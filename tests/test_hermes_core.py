"""Unit tests for hermes_core package."""

import json
import pytest


class TestToolRegistry:
    def test_register_and_dispatch(self):
        from hermes_core.tools import _registry
        names = _registry.get_all_tool_names()
        assert 'read_file' in names
        assert 'write_file' in names
        assert 'terminal' in names
        assert 'todo' in names
        assert 'memory' in names
        assert 'execute_code' in names
        assert len(names) >= 9

    def test_get_definitions_returns_openai_format(self):
        from hermes_core.tools import _registry
        defs = _registry.get_definitions()
        assert len(defs) >= 8
        for d in defs:
            assert d['type'] == 'function'
            assert 'name' in d['function']
            assert 'description' in d['function']
            assert 'parameters' in d['function']

    def test_dispatch_unknown_tool(self):
        from hermes_core.tools import _registry
        result = _registry.dispatch('nonexistent', {})
        data = json.loads(result)
        assert 'error' in data

    def test_get_tool_definitions_with_filters(self):
        from hermes_core.tools import get_tool_definitions
        defs = get_tool_definitions(enabled_toolsets=['file'])
        names = {d['function']['name'] for d in defs}
        assert names == {'read_file', 'write_file', 'patch', 'search_files'}

    def test_handle_function_call(self):
        from hermes_core.tools import handle_function_call
        result = handle_function_call('read_file', {'path': 'hermes_core/__init__.py', 'limit': 2})
        assert 'Hermes Core' in result


class TestFileTools:
    def test_read_file(self):
        from hermes_core.tools.file_tools import read_file
        result = read_file('hermes_core/__init__.py', limit=3)
        assert 'Hermes Core' in result
        assert '1|' in result

    def test_read_file_not_found(self):
        from hermes_core.tools.file_tools import read_file
        result = read_file('/nonexistent/path.txt')
        data = json.loads(result)
        assert 'error' in data

    def test_read_file_directory(self):
        from hermes_core.tools.file_tools import read_file
        result = read_file('hermes_core')
        data = json.loads(result)
        assert 'error' in data

    def test_write_and_read_file(self, tmp_path):
        from hermes_core.tools.file_tools import write_file
        f = tmp_path / 'test.txt'
        result = write_file(str(f), 'hello world')
        data = json.loads(result)
        assert data['success'] is True
        assert f.read_text() == 'hello world'

    def test_write_creates_parent_dirs(self, tmp_path):
        from hermes_core.tools.file_tools import write_file
        f = tmp_path / 'deep' / 'nested' / 'file.txt'
        result = write_file(str(f), 'content')
        data = json.loads(result)
        assert data['success'] is True
        assert f.read_text() == 'content'

    def test_patch_replace(self, tmp_path):
        from hermes_core.tools.file_tools import write_file, patch
        f = tmp_path / 'patch_test.txt'
        write_file(str(f), 'hello world')
        result = patch(str(f), 'hello', 'hi')
        data = json.loads(result)
        assert data['success'] is True
        assert f.read_text() == 'hi world'

    def test_patch_not_found(self, tmp_path):
        from hermes_core.tools.file_tools import write_file, patch
        f = tmp_path / 'patch_test.txt'
        write_file(str(f), 'hello world')
        result = patch(str(f), 'nonexistent', 'replacement')
        data = json.loads(result)
        assert 'error' in data

    def test_patch_multiple_matches(self, tmp_path):
        from hermes_core.tools.file_tools import write_file, patch
        f = tmp_path / 'patch_test.txt'
        write_file(str(f), 'hello hello world')
        result = patch(str(f), 'hello', 'hi')
        data = json.loads(result)
        assert 'error' in data
        assert '2 matches' in data['error']

    def test_patch_replace_all(self, tmp_path):
        from hermes_core.tools.file_tools import write_file, patch
        f = tmp_path / 'patch_test.txt'
        write_file(str(f), 'hello hello world')
        result = patch(str(f), 'hello', 'hi', replace_all=True)
        data = json.loads(result)
        assert data['success'] is True
        assert f.read_text() == 'hi hi world'

    def test_search_files_by_name(self):
        from hermes_core.tools.file_tools import search_files
        result = search_files('*.py', target='files', path='hermes_core', limit=5)
        assert '__init__.py' in result or 'agent.py' in result

    def test_search_files_content(self):
        from hermes_core.tools.file_tools import search_files
        result = search_files('class ToolRegistry', target='content', path='hermes_core', limit=3)
        assert 'ToolRegistry' in result

    def test_search_files_content_files_only(self):
        from hermes_core.tools.file_tools import search_files
        result = search_files('class', target='content', path='hermes_core',
                              output_mode='files_only', limit=5)
        assert '__init__.py' in result or 'agent.py' in result


class TestTerminalTool:
    def test_terminal_simple(self):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('echo hello')
        data = json.loads(result)
        assert data['exit_code'] == 0
        assert 'hello' in data['output']

    def test_terminal_failure(self):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('exit 1')
        data = json.loads(result)
        assert data['exit_code'] == 1

    def test_terminal_stderr(self):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('echo error >&2')
        data = json.loads(result)
        assert 'error' in data['output']

    def test_terminal_timeout(self):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('sleep 5', timeout=1)
        data = json.loads(result)
        assert 'error' in data

    def test_terminal_workdir(self, tmp_path):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('pwd', workdir=str(tmp_path))
        data = json.loads(result)
        assert str(tmp_path) in data['output']

    def test_terminal_background(self):
        from hermes_core.tools.terminal_tool import terminal
        result = terminal('sleep 2 && echo done', background=True)
        data = json.loads(result)
        assert 'session_id' in data
        assert data['status'] == 'running'

    def test_process_list(self):
        from hermes_core.tools.terminal_tool import process
        result = process('list')
        data = json.loads(result)
        assert 'processes' in data or 'message' in data

    def test_process_unknown(self):
        from hermes_core.tools.terminal_tool import process
        result = process('poll', session_id='nonexistent')
        data = json.loads(result)
        assert 'error' in data


class TestMemoryTools:
    def test_todo_read_empty(self):
        from hermes_core.tools.memory_tools import todo
        result = todo()
        data = json.loads(result)
        assert 'todos' in data

    def test_todo_create_and_read(self):
        from hermes_core.tools.memory_tools import todo
        items = [{'id': '1', 'content': 'test item', 'status': 'pending'}]
        r1 = todo(todos=items)
        d1 = json.loads(r1)
        assert len(d1['todos']) == 1
        r2 = todo()
        d2 = json.loads(r2)
        assert len(d2['todos']) == 1
        assert d2['todos'][0]['content'] == 'test item'

    def test_todo_merge(self):
        from hermes_core.tools.memory_tools import todo
        todo(todos=[{'id': '1', 'content': 'first', 'status': 'pending'}])
        todo(todos=[{'id': '2', 'content': 'second', 'status': 'pending'}], merge=True)
        r = todo()
        d = json.loads(r)
        assert len(d['todos']) == 2

    def test_todo_replace(self):
        from hermes_core.tools.memory_tools import todo
        todo(todos=[{'id': 'a', 'content': 'old', 'status': 'pending'}])
        todo(todos=[{'id': 'b', 'content': 'new', 'status': 'in_progress'}], merge=False)
        r = todo()
        d = json.loads(r)
        assert len(d['todos']) == 1
        assert d['todos'][0]['content'] == 'new'

    def test_memory_add(self):
        from hermes_core.tools.memory_tools import memory
        result = memory('add', 'memory', content='test memory entry')
        data = json.loads(result)
        assert data['success'] is True

    def test_memory_add_no_content(self):
        from hermes_core.tools.memory_tools import memory
        result = memory('add', 'memory')
        data = json.loads(result)
        assert 'error' in data

    def test_memory_invalid_target(self):
        from hermes_core.tools.memory_tools import memory
        result = memory('add', 'invalid')
        data = json.loads(result)
        assert 'error' in data

    def test_memory_unknown_action(self):
        from hermes_core.tools.memory_tools import memory
        result = memory('unknown', 'memory')
        data = json.loads(result)
        assert 'error' in data


class TestCodeExecution:
    def test_execute_python(self):
        from hermes_core.tools.code_execution import execute_code
        result = execute_code('print(1 + 1)')
        data = json.loads(result)
        assert data['exit_code'] == 0
        assert '2' in data['output']

    def test_execute_with_error(self):
        from hermes_core.tools.code_execution import execute_code
        result = execute_code('1/0')
        data = json.loads(result)
        assert data['exit_code'] != 0 or 'ZeroDivisionError' in data['output']

    def test_execute_empty_code(self):
        from hermes_core.tools.code_execution import execute_code
        result = execute_code('')
        data = json.loads(result)
        assert 'error' in data


class TestConfig:
    def test_load_default_config(self):
        from hermes_core.config import load_config
        config = load_config()
        assert 'model' in config
        assert 'tools' in config
        assert 'display' in config
        assert 'agent' in config

    def test_config_model_defaults(self):
        from hermes_core.config import load_config
        config = load_config()
        assert 'default' in config['model']
        assert 'max_tokens' in config['model']
        assert 'max_iterations' in config['model']

    def test_config_tools_section(self):
        from hermes_core.config import load_config
        config = load_config()
        assert 'enabled' in config['tools']
        assert 'disabled' in config['tools']


class TestPrompt:
    def test_build_system_prompt(self):
        from hermes_core.prompt import build_system_prompt
        prompt = build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert 'Hermes Agent' in prompt

    def test_build_system_prompt_with_custom(self):
        from hermes_core.prompt import build_system_prompt
        prompt = build_system_prompt(system_message='You are a test bot.')
        assert 'test bot' in prompt

    def test_build_system_prompt_skip_context(self):
        from hermes_core.prompt import build_system_prompt
        prompt = build_system_prompt(skip_context_files=True)
        assert isinstance(prompt, str)
        assert len(prompt) > 50


class TestCompressor:
    def test_compress_messages(self):
        from hermes_core.compressor import compress_messages
        msgs = [{'role': 'user', 'content': 'hello'}]
        result = compress_messages(msgs, model='openai/gpt-4o')
        assert isinstance(result, list)

    def test_compress_messages_with_system(self):
        from hermes_core.compressor import compress_messages
        msgs = [
            {'role': 'system', 'content': 'You are helpful.'},
            {'role': 'user', 'content': 'hi'},
        ]
        result = compress_messages(msgs, model='openai/gpt-4o')
        assert isinstance(result, list)


class TestModels:
    def test_get_model_context_length(self):
        from hermes_core.models import get_model_context_length
        length = get_model_context_length('openai/gpt-4o')
        assert length > 8000

    def test_unknown_model_default(self):
        from hermes_core.models import get_model_context_length
        length = get_model_context_length('unknown/model-123')
        assert length > 0

    def test_estimate_tokens_rough(self):
        from hermes_core.models import estimate_tokens_rough
        tokens = estimate_tokens_rough('hello world')
        assert tokens > 0
        assert tokens < 100

    def test_estimate_tokens_rough_long(self):
        from hermes_core.models import estimate_tokens_rough
        tokens = estimate_tokens_rough('hello ' * 1000)
        assert tokens > 500

    def test_estimate_messages_tokens_rough(self):
        from hermes_core.models import estimate_messages_tokens_rough
        msgs = [{'role': 'user', 'content': 'hello world'}]
        tokens = estimate_messages_tokens_rough(msgs)
        assert tokens > 0

    def test_estimate_request_tokens_rough(self):
        from hermes_core.models import estimate_request_tokens_rough
        msgs = [{'role': 'user', 'content': 'hello'}]
        tokens = estimate_request_tokens_rough(msgs)
        assert tokens > 0


class TestRetry:
    def test_jittered_backoff(self):
        from hermes_core.retry import jittered_backoff
        delay = jittered_backoff(1, base_delay=1.0)
        assert delay >= 1.0
        assert delay <= 3.0

    def test_jittered_backoff_increases(self):
        from hermes_core.retry import jittered_backoff
        d1 = jittered_backoff(1, base_delay=1.0, jitter_ratio=0.0)
        d2 = jittered_backoff(3, base_delay=1.0, jitter_ratio=0.0)
        assert d2 > d1

    def test_jittered_backoff_max(self):
        from hermes_core.retry import jittered_backoff
        delay = jittered_backoff(100, base_delay=1.0, max_delay=120.0, jitter_ratio=0.0)
        assert delay == 120.0


class TestToolsets:
    def test_get_all_toolsets(self):
        from hermes_core.toolsets import get_all_toolsets
        toolsets = get_all_toolsets()
        assert 'file' in toolsets
        assert 'terminal' in toolsets
        assert 'web' in toolsets
        assert 'memory' in toolsets
        assert 'code_execution' in toolsets

    def test_resolve_enabled_tools(self):
        from hermes_core.toolsets import resolve_enabled_tools
        tools = resolve_enabled_tools(['file'])
        assert 'read_file' in tools
        assert 'write_file' in tools
        assert 'terminal' not in tools

    def test_resolve_enabled_tools_all(self):
        from hermes_core.toolsets import resolve_enabled_tools
        tools = resolve_enabled_tools(['core'])
        assert len(tools) >= 9

    def test_validate_toolset(self):
        from hermes_core.toolsets import validate_toolset
        assert validate_toolset('file') is True
        assert validate_toolset('nonexistent') is False
