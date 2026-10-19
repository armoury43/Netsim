"""Tests for netsim.cli.modes."""

from __future__ import annotations

import unittest

from netsim.cli.errors import ModeStackError
from netsim.cli.modes import CliMode, ModeContext, ModeStack


class TestCliMode(unittest.TestCase):
    def test_all_six_required_modes_exist(self) -> None:
        expected = {
            "USER_EXEC",
            "PRIVILEGED_EXEC",
            "GLOBAL_CONFIG",
            "INTERFACE_CONFIG",
            "ROUTER_CONFIG",
            "VLAN_CONFIG",
        }
        actual = {member.name for member in CliMode}
        self.assertEqual(actual, expected)


class TestModeContext(unittest.TestCase):
    def test_defaults_to_empty_params(self) -> None:
        ctx = ModeContext(mode=CliMode.USER_EXEC)
        self.assertEqual(ctx.params, {})

    def test_is_immutable(self) -> None:
        ctx = ModeContext(mode=CliMode.USER_EXEC)
        with self.assertRaises(Exception):
            ctx.mode = CliMode.PRIVILEGED_EXEC


class TestModeStackInitialState(unittest.TestCase):
    def test_starts_in_user_exec(self) -> None:
        stack = ModeStack()
        self.assertEqual(stack.current.mode, CliMode.USER_EXEC)

    def test_initial_prompt_suffix_is_angle_bracket(self) -> None:
        stack = ModeStack()
        self.assertEqual(stack.prompt_suffix(), ">")


class TestModeStackValidTransitions(unittest.TestCase):
    def test_user_exec_to_privileged_exec(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        self.assertEqual(stack.current.mode, CliMode.PRIVILEGED_EXEC)
        self.assertEqual(stack.prompt_suffix(), "#")

    def test_privileged_exec_to_global_config(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        self.assertEqual(stack.current.mode, CliMode.GLOBAL_CONFIG)
        self.assertEqual(stack.prompt_suffix(), "(config)#")

    def test_global_config_to_interface_config_carries_params(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(
            ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": "Gi0/0"})
        )
        self.assertEqual(stack.current.mode, CliMode.INTERFACE_CONFIG)
        self.assertEqual(stack.current.params["interface"], "Gi0/0")
        self.assertEqual(stack.prompt_suffix(), "(config-if)#")

    def test_global_config_to_router_config(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(ModeContext(mode=CliMode.ROUTER_CONFIG, params={"protocol": "rip"}))
        self.assertEqual(stack.prompt_suffix(), "(config-router)#")

    def test_global_config_to_vlan_config(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(ModeContext(mode=CliMode.VLAN_CONFIG, params={"vlan_id": "10"}))
        self.assertEqual(stack.prompt_suffix(), "(config-vlan)#")


class TestModeStackInvalidTransitions(unittest.TestCase):
    def test_cannot_jump_from_user_exec_straight_to_global_config(self) -> None:
        stack = ModeStack()
        with self.assertRaises(ModeStackError):
            stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))

    def test_cannot_jump_from_privileged_exec_straight_to_interface_config(
        self,
    ) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        with self.assertRaises(ModeStackError):
            stack.push(ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": "Gi0/0"}))

    def test_cannot_enter_interface_config_from_router_config(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(ModeContext(mode=CliMode.ROUTER_CONFIG, params={"protocol": "rip"}))
        with self.assertRaises(ModeStackError):
            stack.push(ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": "Gi0/0"}))


class TestModeStackPop(unittest.TestCase):
    def test_pop_returns_to_parent_mode(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(
            ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": "Gi0/0"})
        )
        stack.pop()
        self.assertEqual(stack.current.mode, CliMode.GLOBAL_CONFIG)

    def test_pop_at_base_mode_raises(self) -> None:
        stack = ModeStack()
        with self.assertRaises(ModeStackError):
            stack.pop()

    def test_pop_depth_reports_whether_at_base(self) -> None:
        stack = ModeStack()
        self.assertTrue(stack.at_base_mode())
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        self.assertFalse(stack.at_base_mode())


class TestModeStackPopToPrivileged(unittest.TestCase):
    def test_collapses_any_config_depth_to_privileged_exec(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.push(
            ModeContext(mode=CliMode.INTERFACE_CONFIG, params={"interface": "Gi0/0"})
        )
        stack.pop_to_privileged()
        self.assertEqual(stack.current.mode, CliMode.PRIVILEGED_EXEC)

    def test_is_a_no_op_when_already_at_privileged_exec(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.pop_to_privileged()
        self.assertEqual(stack.current.mode, CliMode.PRIVILEGED_EXEC)

    def test_raises_when_called_from_user_exec(self) -> None:
        stack = ModeStack()
        with self.assertRaises(ModeStackError):
            stack.pop_to_privileged()


class TestModeStackReset(unittest.TestCase):
    def test_reset_returns_to_user_exec(self) -> None:
        stack = ModeStack()
        stack.push(ModeContext(mode=CliMode.PRIVILEGED_EXEC))
        stack.push(ModeContext(mode=CliMode.GLOBAL_CONFIG))
        stack.reset()
        self.assertEqual(stack.current.mode, CliMode.USER_EXEC)
        self.assertTrue(stack.at_base_mode())

if __name__ == "__main__":
    unittest.main()
