#!/bin/bash

YES=0
NO=1
DEBUG=$YES
VERBOSE=$YES
PUPPET=/opt/puppetlabs/bin/puppet


croak() {
    echo "ERROR $*" >&2
    kill -s TERM $BASHPID
    exit 99
}


log() {
  [[ $VERBOSE -eq $YES ]] || return
  echo "INFO $*" >&2
}


debug() {
  [[ $DEBUG -eq $YES ]] || return
  echo "DEBUG (${BASH_SOURCE[1]} [${BASH_LINENO[0]}] ${FUNCNAME[1]}) $*"
}


set_install_dir() {
    [[ $DEBUG -eq $YES ]] && set -x
    INSTALL_DIR=/etc/puppetlabs/enc
    [[ -n "$PUP_ENC_DIR" ]] && INSTALL_DIR="$PUP_ENC_DIR"

    [[ -z "$INSTALL_DIR" ]] \
        && croak "Unable to determine install base. Try setting 'PUP_ENC_DIR' env var."

    [[ -d "$INSTALL_DIR" ]] || mkdir -p $INSTALL_DIR

    [[ -d "$INSTALL_DIR" ]] \
    || croak "Unable to find or create script dir: '$INSTALL_DIR'"
}


ensure_python() {
    [[ $DEBUG -eq $YES ]] && set -x
    PYTHON=$(which python3) 2>/dev/null
    [[ -n "$PY3_PATH" ]] && PYTHON=$PY3_PATH
    [[ -z "$PYTHON" ]] && croak "Unable to find Python3. Try setting 'PY3_PATH' env var."
    PYTHON=$( realpath -e "$PYTHON" )
    [[ -x "$PYTHON" ]] || croak "Found Python3 at '$PYTHON' but it's not executable."
    "$PYTHON" "$BASE/require_py_v3.py" || croak "Python version too low"
    "$PYTHON" -m ensurepip
}


setup_python_venv() {
    [[ $DEBUG -eq $YES ]] && set -x
    venvdir="$INSTALL_DIR/.venv"
    [[ -d "$venvdir" ]] || {
        "$PYTHON" -m venv "$venvdir"
        PIP="$venvdir/bin/pip"
        "$PIP" install --upgrade pip
        "$PIP" install -r "$BASE/requirements.txt"
    }
    V_PYTHON="$venvdir/bin/python"
    [[ -x "$V_PYTHON" ]] || croak "Something went wrong during python venv install."
}


set_shebang_path() {
    [[ $DEBUG -eq $YES ]] && set -x
    newpath="$1"
    shift
    sed -i -e "1 c \#\!$newpath" "$@"
}


install_scripts() {
    [[ $DEBUG -eq $YES ]] && set -x

    # Install admin.py, backup existing if it differs
    set_shebang_path "$V_PYTHON" "$BASE/admin.py"
    install -vbC --suffix="$TS" -t "$INSTALL_DIR" "$BASE/admin.py"

    # Install config files only if they don't already exist
    for fn in tables.yaml config.ini; do
        [[ -f "$INSTALL_DIR/$fn" ]] || cp "$BASE/$fn" "$INSTALL_DIR"
    done
}

configure_puppetserver() {
    # Configure puppetserver to use enc
    # if puppet not installed, don't bother (allows testing on dev node)
    [[ -f "$PUPPET" ]] && {
        $PUPPET config set node_terminus exec --section master
        $PUPPET config set external_nodes "$BASE/admin.py" --section master
    }
}


[[ $DEBUG -eq $YES ]] && set -x
BASE=$(readlink -e $( dirname $0 ) )
TS=$(date +%s)

set_install_dir
log "Installing into: '$INSTALL_DIR'"

ensure_python
debug "Got PYTHON: '$PYTHON'"

setup_python_venv

install_scripts

configure_puppetserver
