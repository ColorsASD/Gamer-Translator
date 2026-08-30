from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "A PowerShell build tesztje Windows környezetet igényel.")
class BuildScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_dir.cleanup)
        self.root_dir = Path(self.temporary_dir.name)
        self.output_dir = self.root_dir / "staging output"
        self.output_dir.mkdir()
        self.old_exe = self.output_dir / "Gamer Translator.exe"
        self.old_exe.write_bytes(b"previous release")
        self.other_exe = self.output_dir / "Other.exe"
        self.other_exe.write_bytes(b"unrelated release")
        self.trace_path = self.root_dir / "calls.txt"
        self.fake_python = self.root_dir / "fake-python.ps1"
        self.fake_python.write_text('''
$module = $args[1]
Add-Content -LiteralPath $env:CORE_BUILD_TRACE -Value $module
if ($env:CORE_BUILD_OBSERVED_PATH) { [IO.File]::WriteAllText($env:CORE_BUILD_OBSERVED_PATH, $env:PATH) }
$global:LASTEXITCODE = 0
if ($module -eq "pip" -and $env:CORE_BUILD_ACTION -eq "fail-pip") {
  $global:LASTEXITCODE = 23
  return
}
if ($module -eq "PyInstaller") {
  if ($env:CORE_BUILD_ACTION -eq "fail-builder") {
    $global:LASTEXITCODE = 17
    return
  }
  if ($env:CORE_BUILD_ACTION -eq "missing-output") { return }
  $index = [Array]::IndexOf($args, "--distpath")
  $distPath = $args[$index + 1]
  New-Item -ItemType Directory -Path $distPath -Force | Out-Null
  [IO.File]::WriteAllText((Join-Path $distPath "Gamer Translator.exe"), "new release")
}
''', encoding="utf-8")

    def run_build(self, action: str, *, skip_install: bool = False) -> subprocess.CompletedProcess:
        build_path = Path(__file__).resolve().parents[1] / "build.ps1"
        command = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(build_path), "-PythonExecutable", str(self.fake_python), "-OutputDirectory", str(self.output_dir)]
        if skip_install:
            command.append("-SkipDependencyInstall")
        environment = dict(os.environ, CORE_BUILD_TRACE=str(self.trace_path), CORE_BUILD_ACTION=action)
        return subprocess.run(command, capture_output=True, text=True, errors="replace", env=environment, timeout=30)

    def assert_previous_files_preserved(self) -> None:
        self.assertEqual(self.old_exe.read_bytes(), b"previous release")
        self.assertEqual(self.other_exe.read_bytes(), b"unrelated release")
        self.assertEqual(list(self.output_dir.glob(".build-*")), [])

    def test_failed_dependency_install_stops_before_build_and_preserves_release(self) -> None:
        result = self.run_build("fail-pip")
        self.assertNotEqual(result.returncode, 0)
        self.assert_previous_files_preserved()
        self.assertEqual(self.trace_path.read_text().splitlines(), ["pip"])

    def test_failed_build_preserves_release_and_cleans_only_staging(self) -> None:
        result = self.run_build("fail-builder", skip_install=True)
        self.assertNotEqual(result.returncode, 0)
        self.assert_previous_files_preserved()
        self.assertEqual(self.trace_path.read_text().splitlines(), ["PyInstaller"])

    def test_missing_output_does_not_replace_release(self) -> None:
        result = self.run_build("missing-output", skip_install=True)
        self.assertNotEqual(result.returncode, 0)
        self.assert_previous_files_preserved()

    def test_successful_build_replaces_only_application_exe(self) -> None:
        result = self.run_build("success", skip_install=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.old_exe.read_text(), "new release")
        self.assertEqual(self.other_exe.read_bytes(), b"unrelated release")
        self.assertEqual(list(self.output_dir.glob(".build-*")), [])

    def test_build_path_excludes_external_tools_and_is_restored_on_failure(self) -> None:
        observed = self.root_dir / "observed-path.txt"
        restored = self.root_dir / "restored-path.txt"
        wrapper = self.root_dir / "run-build.ps1"
        wrapper.write_text('''
try {
  & $env:CORE_BUILD_SCRIPT -PythonExecutable "fake-python.ps1" -OutputDirectory $env:CORE_BUILD_OUTPUT -SkipDependencyInstall
} finally {
  [IO.File]::WriteAllText($env:CORE_BUILD_RESTORED_PATH, $env:PATH)
}
''', encoding="utf-8")
        external = str(self.root_dir / "Külső eszközök Árvíztűrő DLL")
        initial_path = os.pathsep.join([str(self.root_dir), external, os.environ["PATH"]])
        environment = dict(os.environ, PATH=initial_path, CORE_BUILD_TRACE=str(self.trace_path),
                           CORE_BUILD_SCRIPT=str(Path(__file__).resolve().parents[1] / "build.ps1"),
                           CORE_BUILD_OUTPUT=str(self.output_dir), CORE_BUILD_OBSERVED_PATH=str(observed),
                           CORE_BUILD_RESTORED_PATH=str(restored))
        for action in ("success", "fail-builder"):
            with self.subTest(action=action):
                result = subprocess.run([shutil.which("powershell"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
                                        env={**environment, "CORE_BUILD_ACTION": action}, capture_output=True, timeout=30)
                self.assertEqual(result.returncode == 0, action == "success", result.stderr)
                self.assertEqual(restored.read_text(encoding="utf-8"), initial_path)
                actual_paths = {os.path.normcase(path) for path in observed.read_text(encoding="utf-8").split(os.pathsep)}
                expected_paths = {os.path.normcase(str(self.root_dir)), os.path.normcase(os.environ["SYSTEMROOT"]),
                                  os.path.normcase(os.path.join(os.environ["SYSTEMROOT"], "System32"))}
                self.assertEqual(actual_paths, expected_paths)
                self.assertNotIn(os.path.normcase(external), actual_paths)


if __name__ == "__main__":
    unittest.main()
