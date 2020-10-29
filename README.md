# Puppetserver (ENC) External Node Classifier
Setup and manage a database to use for Puppet External Node Classifier

## Dependencies
Required before install:
* Python version >= 3.6

These will be fetched automatically during install:
* https://pypi.org/project/tabulate/
* https://pyyaml.org/wiki/PyYAMLDocumentation

# Installation
1. `export QS_REPO=https://github.com/ncsa/puppetserver-enc.git`
1. `curl https://raw.githubusercontent.com/andylytical/quickstart/master/quickstart.sh | bash`

### Customizable Install Options
- Pull from a branch other than master
`export QS_GIT_BRANCH=branch_name`

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
