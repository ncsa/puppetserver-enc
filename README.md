# Puppetserver (ENC) External Node Classifier
Setup and manage a database to use for Puppet External Node Classifier

## Dependencies
Required before install:
* Python version >= 3.6

These will be fetched automatically during install:
* https://pypi.org/project/tabulate/
* https://pyyaml.org/wiki/PyYAMLDocumentation

# Installation
1. `export PUP_ENC_DIR=/etc/puppetlabs/enc`
1. `git clone https://github.com/ncsa/puppetserver-enc.git $PUP_ENC_DIR`
1. (optional) `vim $PUP_ENC_DIR/config/config.ini`
1. (optional) `export PY3_PATH=</path/to/python3>`
1. `$PUP_ENC_DIR/configure.sh`


# Quickstart
1. `admin.py --help`

### Create DB
1. `vim tables.yaml`
1. `admin.py --init`

### Add self to DB
1. `admin.py --add --fqdn $(hostname -f) $(hostname -f)`

### Add multiple nodes to DB
##### Using a CSV file
1. `admin.py --mkcsv > source.csv`
1. `vim source.csv`
1. `admin.py --add --csv source.csv`
##### Using a Yaml file
1. `admin.py --mkyaml > source.yaml`
1. `vim source.yaml`
1. `admin.py --add --yaml source.yaml`

### Test puppet lookup of FQDN
* `admin.py <FQDN_of_puppet_client_node>`

### List all nodes in DB
* `admin.py -l`

### Working with multiple nodes
All commands `--add`, `--change`, `--del` support input from a yaml or a csv file. This is the best way to specify multiple nodes.
* `admin.py --ch --yaml filename.yaml`
* `admin.py --del --csv filename.csv`
