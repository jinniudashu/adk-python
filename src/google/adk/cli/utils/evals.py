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

from typing import Any

from ...sessions.session import Session


def convert_session_to_eval_format(session: Session) -> list[dict[str, Any]]:
  """Converts a session data into eval format.

  Args:
      session: The session that should be converted.

  Returns:
      list: A single evaluation dataset in the required format.
  """
  eval_case = []
  events = session.events if session and session.events else []

  for event in events:
    if event.author == 'user':
      if not event.content or not event.content.parts:
        continue

      # Extract user query
      content = event.content
      parts = content.parts

      query = parts[0].text or ''

      # Find the corresponding tool usage or response for the query
      expected_tool_use = []
      intermediate_agent_responses = []

      # Check subsequent events to extract tool uses or responses for this turn.
      for subsequent_event in events[events.index(event) + 1 :]:
        event_author = subsequent_event.author or 'agent'
        if event_author == 'user':
          # We found an event where the author was the user. This means that a
          # new turn has started. So close this turn here.
          break

        if not subsequent_event.content or not subsequent_event.content.parts:
          continue

        for subsequent_part in subsequent_event.content.parts:
          # Some events have both function call and reference

          if subsequent_part.function_call:
            tool_name = subsequent_part.function_call.name or ''
            tool_input = subsequent_part.function_call.args or {}
            expected_tool_use.append({
                'tool_name': tool_name,
                'tool_input': tool_input,
            })
          elif subsequent_part.text:
            # Also keep track of all the natural langauge responses that
            # agent (or sub agents) generated.
            intermediate_agent_responses.append(
                {'author': event_author, 'text': subsequent_part.text}
            )

      # If we are here then either we are done reading all the events or we
      # encountered an event that had content authored by the end-user.
      # This, basically means an end of turn.
      # We assume that the last natural langauge intermediate response is the
      # final response from the agent/model. We treat that as a reference.
      eval_case.append({
          'query': query,
          'expected_tool_use': expected_tool_use,
          'expected_intermediate_agent_responses': intermediate_agent_responses[
              :-1
          ],
          'reference': (
              intermediate_agent_responses[-1]['text']
              if intermediate_agent_responses
              else ''
          ),
      })

  return eval_case
