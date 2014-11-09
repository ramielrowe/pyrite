activate_this = '/path/to/venvs/pyrite/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))

from pyrite import APP as application
