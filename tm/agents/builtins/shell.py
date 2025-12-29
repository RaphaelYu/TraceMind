from __future__ import annotations

import os
import shlex
import subprocess
from typing import Iterable, Mapping, Sequence

from tm.agents.runtime import RuntimeAgent


class ShellAgent(RuntimeAgent):
    AGENT_ID = "tm-agent/shell:0.1"

    def run(self, inputs: Mapping[str, object]) -> Mapping[str, object]:
        command = self._resolve_command(inputs)
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=self._execution_env(),
        )
        stdout = process.stdout
        stderr = process.stderr
        result_map = {
            "state:shell.stdout": stdout,
            "state:shell.stderr": stderr,
            "state:shell.exit_code": process.returncode,
        }
        self.add_evidence(
            "builtin.shell",
            {
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": process.returncode,
            },
        )
        outputs: dict[str, object] = {}
        for io_ref in self.contract.outputs:
            outputs[io_ref.ref] = result_map.get(io_ref.ref)
        return outputs

    def _resolve_command(self, inputs: Mapping[str, object]) -> list[str]:
        input_payload = inputs.get("artifact:command")
        raw_command = input_payload or self.config.get("command")
        if raw_command is None:
            raise RuntimeError("shell agent requires a command input")
        if isinstance(raw_command, str):
            return shlex.split(raw_command)
        if isinstance(raw_command, Sequence) and not isinstance(raw_command, str):
            return [str(item) for item in raw_command]
        if isinstance(raw_command, Mapping):
            command_value = raw_command.get("command")
            if command_value is None:
                raise RuntimeError("missing 'command' in shell input mapping")
            args = raw_command.get("args", [])
            return [str(command_value)] + [str(arg) for arg in self._normalize_args(args)]
        raise RuntimeError("unsupported shell command payload")

    def _normalize_args(self, args: object) -> Iterable[object]:
        if isinstance(args, str):
            return shlex.split(args)
        if isinstance(args, Sequence) and not isinstance(args, str):
            return args
        raise RuntimeError("shell args must be a sequence or string")

    def _execution_env(self) -> Mapping[str, str]:
        env = dict(os.environ)
        if "PATH" not in env:
            env["PATH"] = os.defpath
        return env
