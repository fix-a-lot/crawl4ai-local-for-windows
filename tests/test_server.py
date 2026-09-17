import os

import pytest

from crawl4ai_local_for_windows.server import (
    _is_blocked_system_path,
    _parse_field_spec,
)


class TestIsBlockedSystemPath:
    def test_empty_path_is_blocked(self):
        assert _is_blocked_system_path("") is True

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Windows\evil.png",
            r"c:\windows\evil.png",
            r"C:\Windows",
            r"C:\Program Files\evil.png",
            r"C:\Program Files (x86)\evil.png",
            r"C:\ProgramData\evil.png",
            r"C:\Users\All Users\evil.png",
            r"C:\Users\Default\evil.png",
        ],
    )
    def test_blocks_known_absolute_system_paths(self, path):
        assert _is_blocked_system_path(path) is True

    def test_does_not_block_sibling_named_path(self):
        # "C:\Windows2" 는 "C:\Windows"의 하위 디렉터리가 아니다.
        assert _is_blocked_system_path(r"C:\Windows2\evil.png") is False

    def test_does_not_block_ordinary_path(self):
        assert _is_blocked_system_path(r"C:\Users\me\Desktop\shot.png") is False

    def test_blocks_relative_traversal_into_system_path(self, monkeypatch):
        # CWD 기준 상대경로가 실제로는 시스템 경로를 가리키는 경우.
        # abspath로 먼저 절대경로화하지 않으면 이 케이스를 놓친다.
        fake_cwd = r"C:\Users\me\project\deep\nested\dir"
        monkeypatch.setattr(os, "getcwd", lambda: fake_cwd)
        depth = len(fake_cwd.split("\\")) - 1  # 드라이브 루트 제외한 하위 깊이
        traversal = "..\\" * depth + "Windows\\evil.png"
        assert _is_blocked_system_path(traversal) is True


class TestParseFieldSpec:
    def test_attribute_with_selector(self):
        assert _parse_field_spec("a@href") == {
            "name": "",
            "type": "attribute",
            "attribute": "href",
            "selector": "a",
        }

    def test_attribute_on_base_element(self):
        assert _parse_field_spec("@data-value") == {
            "name": "",
            "type": "attribute",
            "attribute": "data-value",
        }

    def test_text_with_explicit_suffix(self):
        assert _parse_field_spec("td:text") == {
            "name": "",
            "type": "text",
            "selector": "td",
        }

    def test_text_without_suffix(self):
        assert _parse_field_spec("td") == {
            "name": "",
            "type": "text",
            "selector": "td",
        }

    def test_text_suffix_only_stripped_at_end(self):
        # selector 자체에 "text"가 부분 문자열로 들어있어도 깨지면 안 된다.
        assert _parse_field_spec(".text-bold:text") == {
            "name": "",
            "type": "text",
            "selector": ".text-bold",
        }
