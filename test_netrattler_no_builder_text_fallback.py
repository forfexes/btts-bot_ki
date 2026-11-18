"""Regression: NETRATTLER never sends a plain-text BET BUILDER
when the user-original card is rejected by its preflight."""
from pathlib import Path
import ast


def test_master_builder_callback_is_image_only():
    source = Path(__file__).with_name("btts_bot.py").read_text(encoding="utf-8")
    root = ast.parse(source)
    callbacks = [node for node in ast.walk(root)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == "_send_builder_pick"]
    assert len(callbacks) == 1
    cb = callbacks[0]
    assert not any(isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id in ("_send_builder", "send_telegram")
                   for node in ast.walk(cb))
    assert any(isinstance(node, ast.Return)
               and isinstance(node.value, ast.Constant)
               and node.value.value is None for node in ast.walk(cb))


def test_model_builder_has_no_text_after_rendering_failure():
    source = Path(__file__).with_name("netrattler_model_builders.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    runner = [node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "run"][0]
    assert not any(isinstance(node, ast.Call)
                   and isinstance(node.func, ast.Name)
                   and node.func.id == "send" for node in ast.walk(runner))
