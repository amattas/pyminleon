#!/bin/bash -eu
# ClusterFuzzLite build: package each fuzz/fuzz_*.py atheris target with its seed corpus and libFuzzer options.
# The builder image runs Python 3.11; pyminleon declares >=3.12 for its supported runtimes but its code runs on 3.11,
# so the fuzz build alone ignores requires-python.
cd "$SRC/pyminleon"
pip3 install --ignore-requires-python .

for fuzzer in fuzz/fuzz_*.py; do
  name=$(basename -s .py "$fuzzer")
  compile_python_fuzzer "$fuzzer"
  zip -j -q "$OUT/${name}_seed_corpus.zip" "fuzz/corpus/$name"/*
  cp "fuzz/$name.options" "$OUT/$name.options"
done
