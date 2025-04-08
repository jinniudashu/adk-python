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


from unittest.mock import AsyncMock
from unittest.mock import Mock
from google.adk.models.lite_llm import _content_to_message_param
from google.adk.models.lite_llm import _function_declaration_to_tool_param
from google.adk.models.lite_llm import _get_content
from google.adk.models.lite_llm import _message_to_generate_content_response
from google.adk.models.lite_llm import _model_response_to_chunk
from google.adk.models.lite_llm import _to_litellm_role
from google.adk.models.lite_llm import FunctionChunk
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.lite_llm import TextChunk
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm import ChatCompletionAssistantMessage
from litellm import ChatCompletionMessageToolCall
from litellm import Function
from litellm.types.utils import ChatCompletionDeltaToolCall
from litellm.types.utils import Choices
from litellm.types.utils import Delta
from litellm.types.utils import ModelResponse
from litellm.types.utils import StreamingChoices
import pytest

LLM_REQUEST_WITH_FUNCTION_DECLARATION = LlmRequest(
    contents=[
        types.Content(
            role="user", parts=[types.Part.from_text(text="Test prompt")]
        )
    ],
    config=types.GenerateContentConfig(
        tools=[
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="test_function",
                        description="Test function description",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "test_arg": types.Schema(
                                    type=types.Type.STRING
                                ),
                                "array_arg": types.Schema(
                                    type=types.Type.ARRAY,
                                    items={
                                        "type": types.Type.STRING,
                                    },
                                ),
                                "nested_arg": types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "nested_key1": types.Schema(
                                            type=types.Type.STRING
                                        ),
                                        "nested_key2": types.Schema(
                                            type=types.Type.STRING
                                        ),
                                    },
                                ),
                            },
                        ),
                    )
                ]
            )
        ],
    ),
)


STREAMING_MODEL_RESPONSE = [
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason=None,
                delta=Delta(
                    role="assistant",
                    content="zero, ",
                ),
            )
        ]
    ),
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason=None,
                delta=Delta(
                    role="assistant",
                    content="one, ",
                ),
            )
        ]
    ),
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason=None,
                delta=Delta(
                    role="assistant",
                    content="two:",
                ),
            )
        ]
    ),
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason=None,
                delta=Delta(
                    role="assistant",
                    tool_calls=[
                        ChatCompletionDeltaToolCall(
                            type="function",
                            id="test_tool_call_id",
                            function=Function(
                                name="test_function",
                                arguments='{"test_arg": "test_',
                            ),
                            index=0,
                        )
                    ],
                ),
            )
        ]
    ),
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason=None,
                delta=Delta(
                    role="assistant",
                    tool_calls=[
                        ChatCompletionDeltaToolCall(
                            type="function",
                            id=None,
                            function=Function(
                                name=None,
                                arguments='value"}',
                            ),
                            index=0,
                        )
                    ],
                ),
            )
        ]
    ),
    ModelResponse(
        choices=[
            StreamingChoices(
                finish_reason="tool_use",
            )
        ]
    ),
]

@pytest.fixture
def mock_response():
  return ModelResponse(
      choices=[
          Choices(
              message=ChatCompletionAssistantMessage(
                  role="assistant",
                  content="Test response",
                  tool_calls=[
                      ChatCompletionMessageToolCall(
                          type="function",
                          id="test_tool_call_id",
                          function=Function(
                              name="test_function",
                              arguments='{"test_arg": "test_value"}',
                          ),
                      )
                  ],
              )
          )
      ]
  )


@pytest.fixture
def mock_acompletion(mock_response):
  return AsyncMock(return_value=mock_response)


@pytest.fixture
def mock_completion(mock_response):
  return Mock(return_value=mock_response)


@pytest.fixture
def mock_client(mock_acompletion, mock_completion):
  return MockLLMClient(mock_acompletion, mock_completion)


@pytest.fixture
def lite_llm_instance(mock_client):
  return LiteLlm(model="test_model", llm_client=mock_client)


class MockLLMClient(LiteLLMClient):

  def __init__(self, acompletion_mock, completion_mock):
    self.acompletion_mock = acompletion_mock
    self.completion_mock = completion_mock

  async def acompletion(self, model, messages, tools, **kwargs):
    return await self.acompletion_mock(
        model=model, messages=messages, tools=tools, **kwargs
    )

  def completion(self, model, messages, tools, stream, **kwargs):
    return self.completion_mock(
        model=model, messages=messages, tools=tools, stream=stream, **kwargs
    )


@pytest.mark.asyncio
async def test_generate_content_async(mock_acompletion, lite_llm_instance):

  async for response in lite_llm_instance.generate_content_async(
      LLM_REQUEST_WITH_FUNCTION_DECLARATION
  ):
    assert response.content.role == "model"
    assert response.content.parts[0].text == "Test response"
    assert response.content.parts[1].function_call.name == "test_function"
    assert response.content.parts[1].function_call.args == {
        "test_arg": "test_value"
    }
    assert response.content.parts[1].function_call.id == "test_tool_call_id"

  mock_acompletion.assert_called_once()

  _, kwargs = mock_acompletion.call_args
  assert kwargs["model"] == "test_model"
  assert kwargs["messages"][0]["role"] == "user"
  assert kwargs["messages"][0]["content"] == "Test prompt"
  assert kwargs["tools"][0]["function"]["name"] == "test_function"
  assert (
      kwargs["tools"][0]["function"]["description"]
      == "Test function description"
  )
  assert (
      kwargs["tools"][0]["function"]["parameters"]["properties"]["test_arg"][
          "type"
      ]
      == "string"
  )


function_declaration_test_cases = [
    (
        "simple_function",
        types.FunctionDeclaration(
            name="test_function",
            description="Test function description",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "test_arg": types.Schema(type=types.Type.STRING),
                    "array_arg": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.STRING,
                        ),
                    ),
                    "nested_arg": types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "nested_key1": types.Schema(type=types.Type.STRING),
                            "nested_key2": types.Schema(type=types.Type.STRING),
                        },
                    ),
                },
            ),
        ),
        {
            "type": "function",
            "function": {
                "name": "test_function",
                "description": "Test function description",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "test_arg": {"type": "string"},
                        "array_arg": {
                            "items": {"type": "string"},
                            "type": "array",
                        },
                        "nested_arg": {
                            "properties": {
                                "nested_key1": {"type": "string"},
                                "nested_key2": {"type": "string"},
                            },
                            "type": "object",
                        },
                    },
                },
            },
        },
    ),
    (
        "no_description",
        types.FunctionDeclaration(
            name="test_function_no_description",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "test_arg": types.Schema(type=types.Type.STRING),
                },
            ),
        ),
        {
            "type": "function",
            "function": {
                "name": "test_function_no_description",
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "test_arg": {"type": "string"},
                    },
                },
            },
        },
    ),
    (
        "empty_parameters",
        types.FunctionDeclaration(
            name="test_function_empty_params",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        {
            "type": "function",
            "function": {
                "name": "test_function_empty_params",
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ),
    (
        "nested_array",
        types.FunctionDeclaration(
            name="test_function_nested_array",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "array_arg": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "nested_key": types.Schema(
                                    type=types.Type.STRING
                                )
                            },
                        ),
                    ),
                },
            ),
        ),
        {
            "type": "function",
            "function": {
                "name": "test_function_nested_array",
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "array_arg": {
                            "items": {
                                "properties": {
                                    "nested_key": {"type": "string"}
                                },
                                "type": "object",
                            },
                            "type": "array",
                        },
                    },
                },
            },
        },
    ),
]


@pytest.mark.parametrize(
    "_, function_declaration, expected_output",
    function_declaration_test_cases,
    ids=[case[0] for case in function_declaration_test_cases],
)
def test_function_declaration_to_tool_param(
    _, function_declaration, expected_output
):
  assert (
      _function_declaration_to_tool_param(function_declaration)
      == expected_output
  )


@pytest.mark.asyncio
async def test_generate_content_async_with_system_instruction(
    lite_llm_instance, mock_acompletion
):
  mock_response_with_system_instruction = ModelResponse(
      choices=[
          Choices(
              message=ChatCompletionAssistantMessage(
                  role="assistant",
                  content="Test response",
              )
          )
      ]
  )
  mock_acompletion.return_value = mock_response_with_system_instruction

  llm_request = LlmRequest(
      contents=[
          types.Content(
              role="user", parts=[types.Part.from_text(text="Test prompt")]
          )
      ],
      config=types.GenerateContentConfig(
          system_instruction="Test system instruction"
      ),
  )

  async for response in lite_llm_instance.generate_content_async(llm_request):
    assert response.content.role == "model"
    assert response.content.parts[0].text == "Test response"

  mock_acompletion.assert_called_once()

  _, kwargs = mock_acompletion.call_args
  assert kwargs["model"] == "test_model"
  assert kwargs["messages"][0]["role"] == "developer"
  assert kwargs["messages"][0]["content"] == "Test system instruction"
  assert kwargs["messages"][1]["role"] == "user"
  assert kwargs["messages"][1]["content"] == "Test prompt"


@pytest.mark.asyncio
async def test_generate_content_async_with_tool_response(
    lite_llm_instance, mock_acompletion
):
  mock_response_with_tool_response = ModelResponse(
      choices=[
          Choices(
              message=ChatCompletionAssistantMessage(
                  role="tool",
                  content='{"result": "test_result"}',
                  tool_call_id="test_tool_call_id",
              )
          )
      ]
  )
  mock_acompletion.return_value = mock_response_with_tool_response

  llm_request = LlmRequest(
      contents=[
          types.Content(
              role="user", parts=[types.Part.from_text(text="Test prompt")]
          ),
          types.Content(
              role="tool",
              parts=[
                  types.Part.from_function_response(
                      name="test_function",
                      response={"result": "test_result"},
                  )
              ],
          ),
      ],
      config=types.GenerateContentConfig(
          system_instruction="test instruction",
      ),
  )
  async for response in lite_llm_instance.generate_content_async(llm_request):
    assert response.content.role == "model"
    assert response.content.parts[0].text == '{"result": "test_result"}'

  mock_acompletion.assert_called_once()

  _, kwargs = mock_acompletion.call_args
  assert kwargs["model"] == "test_model"

  assert kwargs["messages"][2]["role"] == "tool"
  assert kwargs["messages"][2]["content"] == '{"result": "test_result"}'


def test_content_to_message_param_user_message():
  content = types.Content(
      role="user", parts=[types.Part.from_text(text="Test prompt")]
  )
  message = _content_to_message_param(content)
  assert message["role"] == "user"
  assert message["content"] == "Test prompt"


def test_content_to_message_param_assistant_message():
  content = types.Content(
      role="assistant", parts=[types.Part.from_text(text="Test response")]
  )
  message = _content_to_message_param(content)
  assert message["role"] == "assistant"
  assert message["content"] == "Test response"


def test_content_to_message_param_function_call():
  content = types.Content(
      role="assistant",
      parts=[
          types.Part.from_function_call(
              name="test_function", args={"test_arg": "test_value"}
          )
      ],
  )
  content.parts[0].function_call.id = "test_tool_call_id"
  message = _content_to_message_param(content)
  assert message["role"] == "assistant"
  assert message["content"] == []
  assert message["tool_calls"][0].type == "function"
  assert message["tool_calls"][0].id == "test_tool_call_id"
  assert message["tool_calls"][0].function.name == "test_function"
  assert (
      message["tool_calls"][0].function.arguments
      == '{"test_arg": "test_value"}'
  )


def test_message_to_generate_content_response_text():
  message = ChatCompletionAssistantMessage(
      role="assistant",
      content="Test response",
  )
  response = _message_to_generate_content_response(message)
  assert response.content.role == "model"
  assert response.content.parts[0].text == "Test response"


def test_message_to_generate_content_response_tool_call():
  message = ChatCompletionAssistantMessage(
      role="assistant",
      content=None,
      tool_calls=[
          ChatCompletionMessageToolCall(
              type="function",
              id="test_tool_call_id",
              function=Function(
                  name="test_function",
                  arguments='{"test_arg": "test_value"}',
              ),
          )
      ],
  )

  response = _message_to_generate_content_response(message)
  assert response.content.role == "model"
  assert response.content.parts[0].function_call.name == "test_function"
  assert response.content.parts[0].function_call.args == {
      "test_arg": "test_value"
  }
  assert response.content.parts[0].function_call.id == "test_tool_call_id"


def test_get_content_text():
  parts = [types.Part.from_text(text="Test text")]
  content = _get_content(parts)
  assert content == "Test text"


def test_get_content_image():
  parts = [
      types.Part.from_bytes(data=b"test_image_data", mime_type="image/png")
  ]
  content = _get_content(parts)
  assert content[0]["type"] == "image_url"
  assert content[0]["image_url"] == "data:image/png;base64,dGVzdF9pbWFnZV9kYXRh"


def test_get_content_video():
  parts = [
      types.Part.from_bytes(data=b"test_video_data", mime_type="video/mp4")
  ]
  content = _get_content(parts)
  assert content[0]["type"] == "video_url"
  assert content[0]["video_url"] == "data:video/mp4;base64,dGVzdF92aWRlb19kYXRh"


def test_to_litellm_role():
  assert _to_litellm_role("model") == "assistant"
  assert _to_litellm_role("assistant") == "assistant"
  assert _to_litellm_role("user") == "user"
  assert _to_litellm_role(None) == "user"


@pytest.mark.parametrize(
    "response, expected_chunk, expected_finished",
    [
        (
            ModelResponse(
                choices=[
                    {
                        "message": {
                            "content": "this is a test",
                        }
                    }
                ]
            ),
            TextChunk(text="this is a test"),
            "stop",
        ),
        (
            ModelResponse(
                choices=[
                    StreamingChoices(
                        finish_reason=None,
                        delta=Delta(
                            role="assistant",
                            tool_calls=[
                                ChatCompletionDeltaToolCall(
                                    type="function",
                                    id="1",
                                    function=Function(
                                        name="test_function",
                                        arguments='{"key": "va',
                                    ),
                                    index=0,
                                )
                            ],
                        ),
                    )
                ]
            ),
            FunctionChunk(id="1", name="test_function", args='{"key": "va'),
            None,
        ),
        (
            ModelResponse(choices=[{"finish_reason": "tool_calls"}]),
            None,
            "tool_calls",
        ),
        (ModelResponse(choices=[{}]), None, "stop"),
    ],
)
def test_model_response_to_chunk(response, expected_chunk, expected_finished):
  result = list(_model_response_to_chunk(response))
  assert len(result) == 1
  chunk, finished = result[0]
  if expected_chunk:
    assert isinstance(chunk, type(expected_chunk))
    assert chunk == expected_chunk
  else:
    assert chunk is None
  assert finished == expected_finished


@pytest.mark.asyncio
async def test_acompletion_additional_args(mock_acompletion, mock_client):
  lite_llm_instance = LiteLlm(
      # valid args
      model="test_model",
      llm_client=mock_client,
      api_key="test_key",
      api_base="some://url",
      api_version="2024-09-12",
      # invalid args (ignored)
      stream=True,
      messages=[{"role": "invalid", "content": "invalid"}],
      tools=[{
          "type": "function",
          "function": {
              "name": "invalid",
          },
      }],
  )

  async for response in lite_llm_instance.generate_content_async(
      LLM_REQUEST_WITH_FUNCTION_DECLARATION
  ):
    assert response.content.role == "model"
    assert response.content.parts[0].text == "Test response"
    assert response.content.parts[1].function_call.name == "test_function"
    assert response.content.parts[1].function_call.args == {
        "test_arg": "test_value"
    }
    assert response.content.parts[1].function_call.id == "test_tool_call_id"

  mock_acompletion.assert_called_once()

  _, kwargs = mock_acompletion.call_args

  assert kwargs["model"] == "test_model"
  assert kwargs["messages"][0]["role"] == "user"
  assert kwargs["messages"][0]["content"] == "Test prompt"
  assert kwargs["tools"][0]["function"]["name"] == "test_function"
  assert "stream" not in kwargs
  assert "llm_client" not in kwargs
  assert kwargs["api_base"] == "some://url"


@pytest.mark.asyncio
async def test_completion_additional_args(mock_completion, mock_client):
  lite_llm_instance = LiteLlm(
      # valid args
      model="test_model",
      llm_client=mock_client,
      api_key="test_key",
      api_base="some://url",
      api_version="2024-09-12",
      # invalid args (ignored)
      stream=False,
      messages=[{"role": "invalid", "content": "invalid"}],
      tools=[{
          "type": "function",
          "function": {
              "name": "invalid",
          },
      }],
  )

  mock_completion.return_value = iter(STREAMING_MODEL_RESPONSE)

  responses = [
      response
      async for response in lite_llm_instance.generate_content_async(
          LLM_REQUEST_WITH_FUNCTION_DECLARATION, stream=True
      )
  ]
  assert len(responses) == 4
  mock_completion.assert_called_once()

  _, kwargs = mock_completion.call_args

  assert kwargs["model"] == "test_model"
  assert kwargs["messages"][0]["role"] == "user"
  assert kwargs["messages"][0]["content"] == "Test prompt"
  assert kwargs["tools"][0]["function"]["name"] == "test_function"
  assert kwargs["stream"]
  assert "llm_client" not in kwargs
  assert kwargs["api_base"] == "some://url"


@pytest.mark.asyncio
async def test_generate_content_async_stream(
    mock_completion, lite_llm_instance
):

  mock_completion.return_value = iter(STREAMING_MODEL_RESPONSE)

  responses = [
      response
      async for response in lite_llm_instance.generate_content_async(
          LLM_REQUEST_WITH_FUNCTION_DECLARATION, stream=True
      )
  ]
  assert len(responses) == 4
  assert responses[0].content.role == "model"
  assert responses[0].content.parts[0].text == "zero, "
  assert responses[1].content.role == "model"
  assert responses[1].content.parts[0].text == "one, "
  assert responses[2].content.role == "model"
  assert responses[2].content.parts[0].text == "two:"
  assert responses[3].content.role == "model"
  assert responses[3].content.parts[0].function_call.name == "test_function"
  assert responses[3].content.parts[0].function_call.args == {
      "test_arg": "test_value"
  }
  assert responses[3].content.parts[0].function_call.id == "test_tool_call_id"
  mock_completion.assert_called_once()

  _, kwargs = mock_completion.call_args
  assert kwargs["model"] == "test_model"
  assert kwargs["messages"][0]["role"] == "user"
  assert kwargs["messages"][0]["content"] == "Test prompt"
  assert kwargs["tools"][0]["function"]["name"] == "test_function"
  assert (
      kwargs["tools"][0]["function"]["description"]
      == "Test function description"
  )
  assert (
      kwargs["tools"][0]["function"]["parameters"]["properties"]["test_arg"][
          "type"
      ]
      == "string"
  )
