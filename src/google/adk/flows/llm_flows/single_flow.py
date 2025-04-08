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

"""Implementation of single flow."""

import logging

from ...auth import auth_preprocessor
from . import _code_execution
from . import _nl_planning
from . import basic
from . import contents
from . import identity
from . import instructions
from .base_llm_flow import BaseLlmFlow

logger = logging.getLogger(__name__)


class SingleFlow(BaseLlmFlow):
  """SingleFlow is the LLM flows that handles tools calls.

  A single flow only consider an agent itself and tools.
  No sub-agents are allowed for single flow.
  """

  def __init__(self):
    super().__init__()
    self.request_processors += [
        basic.request_processor,
        auth_preprocessor.request_processor,
        instructions.request_processor,
        identity.request_processor,
        contents.request_processor,
        # Some implementations of NL Planning mark planning contents as thoughts
        # in the post processor. Since these need to be unmarked, NL Planning
        # should be after contents.
        _nl_planning.request_processor,
        # Code execution should be after the contents as it mutates the contents
        # to optimize data files.
        _code_execution.request_processor,
    ]
    self.response_processors += [
        _nl_planning.response_processor,
        _code_execution.response_processor,
    ]
