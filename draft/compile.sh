#!/usr/bin/env bash
# Build the dissertation PDFs with host lualatex (the container has no TeX).
#
# Every intermediate file goes to draft/build/<job>/ (git-ignored) and only the PDFs are moved
# back into draft/. Running lualatex by hand inside draft/ leaves .aux/.bbl files there that a
# later build reads silently, which produces a PDF with missing or outdated references, so this
# script refuses to run while such files exist (remove them with `make clean-tex`).
#
# Usage:
#   bash draft/compile.sh                     # main + supplementary (the default)
#   bash draft/compile.sh main                # draft/main.pdf: draft copy, \todo notes, build stamp
#   bash draft/compile.sh review              # draft/review.pdf: copy for the supervisor/committee
#                                             #   (line numbers, wide spacing, no \todo notes, stamp)
#   bash draft/compile.sh submission          # draft/submission.pdf: final layout, no stamp
#   bash draft/compile.sh supplementary       # draft/supplementary.pdf
#   bash draft/compile.sh all                 # main review submission supplementary
#
# Several jobs may be given (`main review`); each runs lualatex, BibTeX when the document cites
# something, lualatex twice, then again while the log asks for a rerun (at most three more
# passes). A failing job does not stop the others. The transcripts stay in
# draft/build/<job>/<job>.log (tools/thesis_check.py reads them) and only file:line errors are
# printed. Each TeX run is limited to THESIS_TEX_TIMEOUT seconds (default 600).
# A job whose previous build did not finish (an error, a timeout, a kill) starts again from an
# empty draft/build/<job>/: a killed run leaves .aux/.toc/.bbl files cut off mid-line.
#
# Exit status: 0 when every PDF was built without undefined references or citations, 1 when a
# job failed or left undefined references or citations (the PDFs are still written), 2 for a
# usage error or stale LaTeX files in draft/.
set -euo pipefail

draft_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
build_root="${draft_dir}/build"

# usage: print the Usage block of the header comment above.
usage() {
  sed -n '/^# Usage:$/,/^#$/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
}

die_usage() {
  echo "compile.sh: $1 (see: bash draft/compile.sh --help)" >&2
  exit 2
}

# --- Arguments --------------------------------------------------------------------------------
jobs=()
add_job() {
  local job="$1" existing
  for existing in "${jobs[@]+"${jobs[@]}"}"; do
    [ "${existing}" = "${job}" ] && return 0
  done
  jobs+=("${job}")
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    main | review | submission | supplementary) add_job "$1" ;;
    all) for job in main review submission supplementary; do add_job "${job}"; done ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die_usage "unknown job or option '$1'" ;;
  esac
  shift
done
if [ "${#jobs[@]}" -eq 0 ]; then
  jobs=(main supplementary)
fi

# --- Stale files from builds inside draft/ ----------------------------------------------------
stale="$(find "${draft_dir}" -path "${build_root}" -prune -o -type f \
  \( -name '*.aux' -o -name '*.bbl' -o -name '*.toc' -o -name '*.lof' -o -name '*.lot' \
  -o -name '*.out' -o -name '*.blg' -o -name '*.fls' -o -name '*.fdb_latexmk' \) -print)"
if [ -n "${stale}" ]; then
  echo "stale LaTeX files in draft/: run make clean-tex" >&2
  printf '%s\n' "${stale}" | sed "s|^${draft_dir}/|  draft/|" | head -n 20 >&2
  exit 2
fi

command -v lualatex > /dev/null 2>&1 || {
  echo "compile.sh: lualatex not found; install TeX Live on the host (see README.md)" >&2
  exit 1
}

# --- Shared settings --------------------------------------------------------------------------
# One message per log line, so file:line errors and warnings stay greppable.
export max_print_line=10000
tex_timeout=()
if command -v timeout > /dev/null 2>&1; then
  # --foreground (GNU) keeps lualatex in the terminal's process group so Ctrl-C still stops it.
  if timeout --foreground 5 true > /dev/null 2>&1; then
    tex_timeout=(timeout --foreground "${THESIS_TEX_TIMEOUT:-600}")
  else
    tex_timeout=(timeout "${THESIS_TEX_TIMEOUT:-600}")
  fi
fi
# The caller's search paths, kept so that nested builds do not stack their directories.
base_texinputs="${TEXINPUTS:-}"
base_bibinputs="${BIBINPUTS:-}"
base_bstinputs="${BSTINPUTS:-}"

# Build stamp printed on draft and review copies: which commit the reader is looking at.
stamp_commit="unknown"
if command -v git > /dev/null 2>&1 &&
  commit="$(git -C "${draft_dir}" rev-parse --short HEAD 2> /dev/null)"; then
  stamp_commit="${commit}"
  if [ -n "$(git -C "${draft_dir}" status --porcelain 2> /dev/null)" ]; then
    stamp_commit="${stamp_commit}-dirty"
  fi
fi
stamp="${stamp_commit} $(date +%Y-%m-%d)"

# --- Helpers (each job runs in its own subshell with errexit) ---------------------------------

# cites <job_dir> <aux>: true if the .aux file, or one it pulls in with \@input (as \include
# does), records a citation.
cites() {
  local dir="$1" aux="$2" child
  grep -q '\\citation' "${aux}" && return 0
  while IFS= read -r child; do
    if [ -f "${dir}/${child}" ] && cites "${dir}" "${dir}/${child}"; then
      return 0
    fi
  done < <(sed -n 's/^\\@input{\(.*\)}$/\1/p' "${aux}")
  return 1
}

# run_tex <job_dir> <name> <source>: one lualatex pass with the transcript in the log only.
run_tex() {
  local dir="$1" name="$2" source="$3" status=0
  "${tex_timeout[@]+"${tex_timeout[@]}"}" lualatex -interaction=nonstopmode -halt-on-error \
    -file-line-error -output-directory="${dir}" -jobname="${name}" "${source}" \
    < /dev/null > /dev/null || status=$?
  if [ "${status}" -eq 124 ] && [ "${#tex_timeout[@]}" -gt 0 ]; then
    echo "lualatex timed out after ${THESIS_TEX_TIMEOUT:-600} s on ${name} (THESIS_TEX_TIMEOUT)" >&2
    exit 1
  elif [ "${status}" -ne 0 ]; then
    echo "lualatex failed on ${name} (draft/build/${name}/${name}.log):" >&2
    grep -E -A 3 '^[^ ]+:[0-9]+: |^! ' "${dir}/${name}.log" >&2 ||
      tail -n 30 "${dir}/${name}.log" >&2
    exit 1
  fi
}

# build <name> <source>: lualatex, BibTeX when the document has a bibliography and cites
# something, lualatex twice more and again while the log asks for a rerun (at most three more
# passes: a fresh review copy needs one for lineno's page-wise line numbers), then move the PDF
# to draft/<name>.pdf.
build() {
  local name="$1" source="$2" pdf="$1.pdf" dir="${build_root}/$1" status=0 pages n=0
  echo "Building ${pdf}"
  # Unless the last build of this job completed, start from an empty directory. A lualatex or
  # BibTeX run stopped by THESIS_TEX_TIMEOUT, a kill or a closed terminal leaves its files cut
  # off mid-line, and a failed run can leave a .toc/.lof entry that breaks the next run; TeX
  # reads both at \begin{document} before rewriting them, so every later build would stop
  # there even after the source is fixed. The passes below rebuild every auxiliary file.
  if [ ! -f "${dir}/.build-complete" ]; then
    rm -rf "${dir}"
  fi
  mkdir -p "${dir}"
  # Present only after a complete, successful build.
  rm -f "${dir}/.build-complete"
  # \include{chapters/x} writes <dir>/chapters/x.aux and TeX does not create that directory
  # itself: mirror the subdirectories of draft/.
  (cd "${draft_dir}" && find . -mindepth 1 -type d ! -path './build' ! -path './build/*' -print0) |
    while IFS= read -r -d '' sub; do
      mkdir -p "${dir}/${sub#./}"
    done
  # Let TeX and BibTeX find sources, bibliographies and .bst files in draft/ while writing
  # everything to the job's build directory.
  export TEXINPUTS="${dir}:${draft_dir}:${base_texinputs}"
  export BIBINPUTS="${draft_dir}:${base_bibinputs}"
  export BSTINPUTS="${draft_dir}:${base_bstinputs}"
  cd "${draft_dir}"
  run_tex "${dir}" "${name}" "${source}"
  if grep -q '\\bibdata' "${dir}/${name}.aux" && cites "${dir}" "${dir}/${name}.aux"; then
    # BibTeX exits 1 for warnings (an empty field, for example) and 2 or more for errors.
    # Warnings are printed; only errors stop the job. The full transcript is in the .blg.
    (cd "${dir}" && "${tex_timeout[@]+"${tex_timeout[@]}"}" bibtex "${name}" \
      < /dev/null > "${dir}/${name}.bibtex-stdout") || status=$?
    if [ "${status}" -eq 1 ]; then
      grep -E '^Warning--|^--line ' "${dir}/${name}.bibtex-stdout" >&2 || true
    elif [ "${status}" -gt 1 ]; then
      cat "${dir}/${name}.bibtex-stdout" >&2
      echo "bibtex failed on ${name} (draft/build/${name}/${name}.blg)" >&2
      exit 1
    fi
  else
    # Without BibTeX, a .bbl left by an earlier build would still list references the
    # document no longer cites.
    rm -f "${dir}/${name}.bbl"
  fi
  run_tex "${dir}" "${name}" "${source}"
  run_tex "${dir}" "${name}" "${source}"
  while [ "${n}" -lt 3 ] && grep -qE 'Rerun to get|re-run to get it right' "${dir}/${name}.log"; do
    run_tex "${dir}" "${name}" "${source}"
    n=$((n + 1))
  done
  mv "${dir}/${name}.pdf" "${draft_dir}/${pdf}"
  touch "${dir}/.build-complete"
  pages=""
  if command -v pdfinfo > /dev/null 2>&1; then
    pages="$(pdfinfo "${draft_dir}/${pdf}" 2> /dev/null | awk '/^Pages:/ {print $2}')"
  fi
  if [ "${pages}" = "1" ]; then
    echo "Built draft/${pdf} (1 page)"
  elif [ -n "${pages}" ]; then
    echo "Built draft/${pdf} (${pages} pages)"
  else
    echo "Built draft/${pdf}"
  fi
}

# --- Jobs -------------------------------------------------------------------------------------
failed=()
built=()
for job in "${jobs[@]}"; do
  case "${job}" in
    main) source='\def\ThesisBuildStamp{'"${stamp}"'}\input{main.tex}' ;;
    review) source='\def\ThesisBuildStamp{'"${stamp}"'}\input{review.tex}' ;;
    submission) source='\input{submission.tex}' ;;
    supplementary) source='\input{supplementary.tex}' ;;
  esac
  set +e
  (
    set -e
    build "${job}" "${source}"
  )
  status=$?
  set -e
  if [ "${status}" -eq 0 ]; then
    built+=("${job}")
  else
    failed+=("${job}")
  fi
done

# TeX exits 0 when a citation or a reference is undefined, so read what the last pass reported.
status=0
for name in "${built[@]+"${built[@]}"}"; do
  log="${build_root}/${name}/${name}.log"
  if grep -E '(Citation|Reference) .*undefined|There were undefined' "${log}" >&2; then
    echo "Undefined citations or references in ${name}: see draft/build/${name}/${name}.log" >&2
    status=1
  fi
  if grep -q 'Package thesis Warning: Values file' "${log}"; then
    echo "Note: ${name} registers values files that do not exist (draft/values.tex): fix the" \
      "path, copy projects/_template/values.tex to projects/<id>/values.tex, or delete the line" >&2
  fi
  if grep -q 'Package thesis Warning: Undefined value' "${log}"; then
    echo "Note: ${name} uses undefined \\val keys, typeset as ??: run make check" >&2
  fi
done
if [ "${#failed[@]}" -gt 0 ]; then
  echo "Failed: ${failed[*]}" >&2
  status=1
fi
exit "${status}"
