# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import time
from typing import Any
from typing import Optional
import uuid

from typing_extensions import override

from ..events.event import Event
from .base_session_service import BaseSessionService
from .base_session_service import GetSessionConfig
from .base_session_service import ListEventsResponse
from .base_session_service import ListSessionsResponse
from .session import Session
from .state import State


class InMemorySessionService(BaseSessionService):
  """An in-memory implementation of the session service."""

  def __init__(self):
    # A map from app name to a map from user ID to a map from session ID to session.
    self.sessions: dict[str, dict[str, dict[str, Session]]] = {}
    # A map from app name to a map from user ID to a map from key to the value.
    self.user_state: dict[str, dict[str, dict[str, Any]]] = {}
    # A map from app name to a map from key to the value.
    self.app_state: dict[str, dict[str, Any]] = {}

  @override
  def create_session(
      self,
      *,
      app_name: str,
      user_id: str,
      state: Optional[dict[str, Any]] = None,
      session_id: Optional[str] = None,
  ) -> Session:
    session_id = (
        session_id.strip()
        if session_id and session_id.strip()
        else str(uuid.uuid4())
    )
    session = Session(
        app_name=app_name,
        user_id=user_id,
        id=session_id,
        state=state or {},
        last_update_time=time.time(),
    )

    if app_name not in self.sessions:
      self.sessions[app_name] = {}
    if user_id not in self.sessions[app_name]:
      self.sessions[app_name][user_id] = {}
    self.sessions[app_name][user_id][session_id] = session

    copied_session = copy.deepcopy(session)
    return self._merge_state(app_name, user_id, copied_session)

  @override
  def get_session(
      self,
      *,
      app_name: str,
      user_id: str,
      session_id: str,
      config: Optional[GetSessionConfig] = None,
  ) -> Session:
    if app_name not in self.sessions:
      return None
    if user_id not in self.sessions[app_name]:
      return None
    if session_id not in self.sessions[app_name][user_id]:
      return None

    session = self.sessions[app_name][user_id].get(session_id)
    copied_session = copy.deepcopy(session)

    if config:
      if config.num_recent_events:
        copied_session.events = copied_session.events[
            -config.num_recent_events :
        ]
      elif config.after_timestamp:
        i = len(session.events) - 1
        while i >= 0:
          if copied_session.events[i].timestamp < config.after_timestamp:
            break
          i -= 1
        if i >= 0:
          copied_session.events = copied_session.events[i:]

    return self._merge_state(app_name, user_id, copied_session)

  def _merge_state(self, app_name: str, user_id: str, copied_session: Session):
    # Merge app state
    if app_name in self.app_state:
      for key in self.app_state[app_name].keys():
        copied_session.state[State.APP_PREFIX + key] = self.app_state[app_name][
            key
        ]

    if (
        app_name not in self.user_state
        or user_id not in self.user_state[app_name]
    ):
      return copied_session

    # Merge session state with user state.
    for key in self.user_state[app_name][user_id].keys():
      copied_session.state[State.USER_PREFIX + key] = self.user_state[app_name][
          user_id
      ][key]
    return copied_session

  @override
  def list_sessions(
      self, *, app_name: str, user_id: str
  ) -> ListSessionsResponse:
    empty_response = ListSessionsResponse()
    if app_name not in self.sessions:
      return empty_response
    if user_id not in self.sessions[app_name]:
      return empty_response

    sessions_without_events = []
    for session in self.sessions[app_name][user_id].values():
      copied_session = copy.deepcopy(session)
      copied_session.events = []
      copied_session.state = {}
      sessions_without_events.append(copied_session)
    return ListSessionsResponse(sessions=sessions_without_events)

  @override
  def delete_session(
      self, *, app_name: str, user_id: str, session_id: str
  ) -> None:
    if (
        self.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        is None
    ):
      return None

    self.sessions[app_name][user_id].pop(session_id)

  @override
  def append_event(self, session: Session, event: Event) -> Event:
    # Update the in-memory session.
    super().append_event(session=session, event=event)
    session.last_update_time = event.timestamp

    # Update the storage session
    app_name = session.app_name
    user_id = session.user_id
    session_id = session.id
    if app_name not in self.sessions:
      return event
    if user_id not in self.sessions[app_name]:
      return event
    if session_id not in self.sessions[app_name][user_id]:
      return event

    if event.actions and event.actions.state_delta:
      for key in event.actions.state_delta:
        if key.startswith(State.APP_PREFIX):
          self.app_state.setdefault(app_name, {})[
              key.removeprefix(State.APP_PREFIX)
          ] = event.actions.state_delta[key]

        if key.startswith(State.USER_PREFIX):
          self.user_state.setdefault(app_name, {}).setdefault(user_id, {})[
              key.removeprefix(State.USER_PREFIX)
          ] = event.actions.state_delta[key]

    storage_session = self.sessions[app_name][user_id].get(session_id)
    super().append_event(session=storage_session, event=event)

    storage_session.last_update_time = event.timestamp

    return event

  @override
  def list_events(
      self,
      *,
      app_name: str,
      user_id: str,
      session_id: str,
  ) -> ListEventsResponse:
    raise NotImplementedError()
