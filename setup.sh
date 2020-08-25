#!/bin/bash

DEBUG=1
PUPPET=/opt/puppetlabs/bin/puppet


die() {
    echo "ERROR: $*" >&2
    exit 2
}


set_shebang_path() {
    [[ $DEBUG -gt 0 ]] && set -x
    newpath="$1"
    shift
    sed -i -e "1 c \#\!$newpath" "$@"
}


[[ $DEBUG -gt 0 ]] && set -x

# Get install directory
BASE=$(readlink -e $( dirname $0 ) ) 
[[ -n "$PUP_ENC_DIR" ]] && BASE="$PUP_ENC_DIR"
[[ -z "$BASE" ]] && die "Unable to determine install base. Try setting PUP_ENC_DIR env var."

# Find python3
[[ -z "$PYTHON" ]] && PYTHON=$(which python3) 2>/dev/null
[[ -n "$PY3_PATH" ]] && PYTHON=$PY3_PATH
[[ -z "$PYTHON" ]] && die "Unable to find Python3. Try setting PY3_PATH env var."

# Verify python is version 3
"$PYTHON" "$BASE/require_py_v3.py" || die "Python version too low"

# Setup python virtual env
venvdir="$BASE/.venv"
[[ -d "$venvdir" ]] || {
    "$PYTHON" -m venv "$venvdir"
    PIP="$venvdir/bin/pip"
    "$PIP" install --upgrade pip
    "$PIP" install -r "$BASE/requirements.txt"
}
V_PYTHON="$venvdir/bin/python"
[[ -x "$V_PYTHON" ]] || die "Something went wrong during python venv install."

###
# Setup ENC
###
ENC_FN="$BASE/enc/admin.py"

# Configure admin.py to use venv python
set_shebang_path "$V_PYTHON" "$ENC_FN"

# Configure puppetserver to use enc
# if puppet not installed, don't bother (allows testing on dev node)
[[ -f "$PUPPET" ]] && {
    $PUPPET config set node_terminus exec --section master
    $PUPPET config set external_nodes "$ENC_FN" --section master
}

# Create shortcut symlinks for enc admin
for l in enc_admin enc_adm; do
    lname="/usr/local/sbin/$l"
    [[ -f "$lname" ]] \
    || ln -s "$ENC_FN" "$lname"
done
