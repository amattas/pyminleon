#!/bin/bash -eu
# Builds every fuzz/fuzz_*.py atheris target, its seed corpus, and its libFuzzer options into $OUT.

python3 -m pip install --no-cache-dir .

for fuzzer in fuzz/fuzz_*.py; do
  name=$(basename -s .py "$fuzzer")
  compile_python_fuzzer "$fuzzer"
  (cd "fuzz/corpus/$name" && zip -q -r "$OUT/${name}_seed_corpus.zip" .)
  cp "fuzz/$name.options" "$OUT/$name.options"
done
