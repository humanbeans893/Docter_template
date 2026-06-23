# projects/

Each subdirectory here is one **self-contained study** of the dissertation.
A study holds its own code, data, and outputs and does not depend on sibling
studies. The integrated thesis manuscript lives in the repo-root `draft/`, where
each study typically becomes one chapter.

## Layout of a study

```text
projects/<study>/
├── data/{raw,interim,processed}/   # study-local data (gitignored except structure)
├── src/{utils,models,methods,analysis}/
├── scripts/                        # reproducible entry points
├── result/{figures,tables,animations}/
├── config.py                       # study-local paths + shared constants
└── README.md
```

## Add a new study

Copy the template directory and rename it:

```bash
cp -r projects/_template projects/<your-study-name>
```

Then point the thesis at it by adding a `\graphicspath` entry in
`draft/preamble.tex` and an `\include{chapters/NN-<study>}` line in
`draft/main.tex`.

## Why a monorepo (not git submodules)

All studies share this single git repository. We deliberately avoid nesting git
repositories (submodules/subtrees): for a solo dissertation they add operational
overhead (detached HEAD, two-step commits, clone gotchas) without benefit.

If a study later needs to become a standalone public repository, extract it with
its history at that point:

```bash
git subtree split --prefix=projects/<study> -b <study>-export
# or, for a full rewrite: git filter-repo --path projects/<study>/
```
