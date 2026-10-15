"""Run the standard pipeline, prepare replicates or rebuild pooled outputs.

    python -m census.run_all
    python -m census.run_all --no-figures
    python -m census.run_all --replicates
    python -m census.run_all --pool

The standard run builds processed data and, in the manuscript checkout, figures
and Supplementary Information tables. `--replicates` runs the automated draw,
retrieval, audit, validation-item and summary stages. Annotation uses a manual
hand-off through an external agent harness: run the `batches` and `collect`
commands in `census.validation.label_replicates` and
`census.validation.label_round2` for the two rounds.
`--pool` runs `python -m census.validation.replicates pool` followed by
`python -m census.validation.label_round2 pooled`, then the offline area audit
(`python -m census.validation.audit_by_area`). It rebuilds all pooled outputs from
the committed label CSVs and replicate records without invoking annotators.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from census._paths import FIGURES_DIR, SCRIPTS_DIR

def figure_scripts() -> list[str]:
    """Main then supplementary figure scripts, found by name (FigureN__*.py,
    SFigureN__*.py) so renaming a figure in the manuscript needs no edit here."""
    if not FIGURES_DIR.exists():
        return []
    def key(p):
        num = p.name.split("__")[0].lstrip("SFigure")
        return (p.name.startswith("S"), int(num) if num.isdigit() else 99)
    paths = [p for p in FIGURES_DIR.glob("*Figure*__*.py") if p.name[0] in "FS"]
    return [p.name for p in sorted(paths, key=key)]


def run_figures() -> None:
    for name in figure_scripts():
        path = FIGURES_DIR / name
        if not path.exists():
            print(f"[skip] {name} (not found)")
            continue
        print(f"[figure] {name}")
        subprocess.run([sys.executable, str(path)], check=True, cwd=SCRIPTS_DIR)


def optional_commands(audit: bool, draws: list[str], seed: str) -> list[list[str]]:
    """Opt-in generation only. Annotation and validation scoring stay manual."""
    commands = []
    if audit:
        commands.extend([['-m', 'census.build.build_reporting_audit'],
                         ['-m', 'census.validation.validate_reporting_audit', 'sample']])
    for name in draws:
        commands.append(['-m', 'census.validation.draw_validation_samples', name, '--seed', seed])
    return commands


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lit-only", action="store_true")
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--sample-cap", type=int, default=200)
    ap.add_argument('--audit', action='store_true',
                    help='build reporting audit and draw its annotation items; scoring stays manual')
    ap.add_argument('--draw-validation', nargs='+', choices=['cellpose', 'alias', 'lexicon', 'domains'], default=[],
                    help='draw fresh identifier lists only, without changing labels')
    ap.add_argument('--validation-seed', default='20261006-validation-redraw-v1',
                    help='recorded string seed for fresh validation draws')
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument('--replicates', action='store_true',
                       help='run automated replicate preparation only')
    modes.add_argument('--pool', action='store_true',
                       help='rebuild all pooled outputs from committed labels and replicate records')
    args = ap.parse_args()
    if args.pool:
        for module, command in (('census.validation.replicates', 'pool'),
                                ('census.validation.label_round2', 'pooled')):
            subprocess.run([sys.executable, '-m', module, command], check=True, cwd=SCRIPTS_DIR)
        subprocess.run([sys.executable, '-m', 'census.validation.audit_by_area'], check=True, cwd=SCRIPTS_DIR)
        return
    if args.replicates:
        for step in ('draw', 'abstracts', 'audit', 'validation', 'summarise'):
            subprocess.run([sys.executable, '-m', 'census.validation.replicates', step], check=True, cwd=SCRIPTS_DIR)
        return

    from census.build import build_dataset

    build_argv = ["build_dataset.py", "--sample-cap", str(args.sample_cap)]
    if args.lit_only:
        build_argv.append("--lit-only")
    sys.argv = build_argv
    build_dataset.main()

    if not args.lit_only:
        # Second deep-learning estimator and the random corpus for Figure 5.
        for step in ("census.build.build_dataset_dl_in_tools", "census.build.random_corpus",
                     "census.build.build_hosts", "census.build.build_methods_check",
                     "census.build.build_sensitivity"):
            subprocess.run([sys.executable, "-m", step], check=True, cwd=SCRIPTS_DIR)
    for command in optional_commands(args.audit, args.draw_validation, args.validation_seed):
        subprocess.run([sys.executable, *command], check=True, cwd=SCRIPTS_DIR)
    if not args.lit_only and not args.no_figures:
        run_figures()
        subprocess.run([sys.executable, "-m", "census.tables.make_si_tables"], check=True, cwd=SCRIPTS_DIR)
    print("done.")


if __name__ == "__main__":
    main()
