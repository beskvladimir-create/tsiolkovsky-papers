#!/bin/bash
# Copies the published files into the working directory.
#
# The working directory holds the scans, the transcription queue and the
# private planning notes; this repository holds what is published. The two
# shared the same scripts as separate copies until they quietly diverged and a
# fix landed in only one of them. This makes the direction explicit: the
# repository is the source, the working directory is a copy.
#
#   ./sync.sh ../tsiolkovsky-archive

DEST="${1:-../tsiolkovsky-archive}"
[ -d "$DEST" ] || { echo "no such directory: $DEST"; exit 1; }
cd "$(dirname "$0")" || exit 1

n=0
for f in $(git ls-files | grep -E '\.(py|sh)$'); do
    [ "$f" = "sync.sh" ] && continue
    if ! cmp -s "$f" "$DEST/$f"; then
        cp "$f" "$DEST/$f"
        echo "  updated: $f"
        n=$((n+1))
    fi
done
echo "  files copied: $n"
