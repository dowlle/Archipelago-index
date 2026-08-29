#!/usr/bin/env python3
"""Smoke-test an APWorld with Archipelago's generated default template.

This is intentionally a core-generation check (``Generate.py --skip_output``).
It proves that the package can load, roll its canonical options, create its
regions and items, and fill a seed without requiring user-owned ROMs or calling
an output stage. A pass does not override failures found by fuzzing or full
generation; it only prevents random-option failures from being labelled
"never generates".
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path


def target_games(module: str) -> list[str]:
    # The script lives in the index checkout while it is executed with the
    # Archipelago checkout as cwd. Make that checkout importable explicitly.
    sys.path.insert(0, str(Path.cwd()))
    import worlds  # noqa: F401  # imports custom .apworlds and registers games
    from worlds.AutoWorld import AutoWorldRegister

    prefix = f"worlds.{module}"
    return sorted(
        game
        for game, world in AutoWorldRegister.world_types.items()
        if world.__module__ == prefix or world.__module__.startswith(prefix + ".")
    )


def run_check(module: str, artifact_dir: Path, seed: int) -> int:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "canonical-smoke.json"
    results: dict = {"module": module, "seed": seed, "mode": "canonical-core", "games": []}

    try:
        games = target_games(module)
        if not games:
            raise RuntimeError(f"No registered game belongs to worlds.{module}")

        from Options import generate_yaml_templates
        from Utils import get_file_safe_name

        with tempfile.TemporaryDirectory(prefix="canonical-templates-") as template_tmp:
            template_dir = Path(template_tmp)
            # Hidden worlds still need a gate result; visibility is unrelated
            # to whether their canonical option set can generate.
            generate_yaml_templates(template_dir, True)

            for position, game in enumerate(games, start=1):
                template = template_dir / f"{get_file_safe_name(game)}.yaml"
                if not template.is_file():
                    raise RuntimeError(f"Canonical template was not emitted for {game}: {template}")

                game_dir = artifact_dir / f"game-{position}"
                player_dir = game_dir / "players"
                output_dir = game_dir / "output"
                player_dir.mkdir(parents=True, exist_ok=True)
                output_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(template, player_dir / "Player1.yaml")

                command = [
                    sys.executable,
                    "Generate.py",
                    "--player_files_path", str(player_dir),
                    "--outputpath", str(output_dir),
                    "--seed", str(seed),
                    "--multi", "1",
                    "--spoiler", "0",
                    "--skip_output",
                ]
                completed = subprocess.run(command, text=True, capture_output=True)
                log = completed.stdout + completed.stderr
                (game_dir / "generation.log").write_text(log, encoding="utf-8")
                print(f"=== canonical default: {game} ===")
                print(log, end="" if log.endswith("\n") else "\n")

                results["games"].append({
                    "game": game,
                    "template": template.name,
                    "returncode": completed.returncode,
                })
                if completed.returncode:
                    results["status"] = "failed"
                    result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
                    return completed.returncode

        results["status"] = "passed"
        result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"Canonical core generation passed for {len(games)} game(s): {', '.join(games)}")
        return 0
    except Exception as exc:
        results["status"] = "error"
        results["error"] = f"{type(exc).__name__}: {exc}"
        result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        traceback.print_exc()
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, help="inner APWorld module name")
    parser.add_argument("--artifact-dir", type=Path, default=Path("canonical_output"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    return run_check(args.module, args.artifact_dir.resolve(), args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
