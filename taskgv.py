#!/usr/bin/env python
'graph dependencies in projects'
import json
from subprocess import Popen, PIPE
import subprocess
import sys
import textwrap
from distutils import spawn
from tempfile import mkstemp
from os import fdopen

# Typical command line usage:
#
# taskgv TASKFILTER
#
# TASKFILTER is a taskwarrior filter, documentation can be found here: http://taskwarrior.org/projects/taskwarrior/wiki/Feature_filters
#
# Probably the most helpful commands are:
#
# taskgv project:fooproject status:pending
#  --> graph pending tasks in project 'fooproject'
#
# taskgv project:fooproject
#  --> graphs all tasks in 'fooproject', pending, completed, deleted
#
# taskgv status:pending
#  --> graphs all pending tasks in all projects
#
# taskgv
#  --> graphs everything - could be massive

# Wrap label text at this number of characters.
charsPerLine = 20;

# Full list of colors here: http://www.graphviz.org/doc/info/colors.html
blockedColor = 'gold4'
maxUrgencyColor = 'red2'
unblockedColor = 'green'
doneColor = 'grey'
waitColor = 'white'
deletedColor = 'pink';

# The width of the border around the tasks:
penWidth = 1

# Let arrow direction show implication.
dir = 'back'

# Have one HEADER (and only one) uncommented at a time, or the last uncommented value will be the only one considered.

# Left to right layout:
#HEADER = "digraph  dependencies { splines=true; overlap=ortho; rankdir=LR; weight=2;"

# Spread tasks on page:
HEADER = "digraph  dependencies { layout=neato;   splines=true; overlap=scalexy;  rankdir=LR; weight=2; esep=0.5;"

# More information on setting up Graphviz: http://www.graphviz.org/doc/info/attrs.html

#-----------------------------------------#
#  Editing under this might break things  #
#-----------------------------------------#

FOOTER = "}"

JSON_START = '['
JSON_END = ']'

validUuids = list()

def call_taskwarrior(cmd):
    'call taskwarrior, returning output and error'
    tw = Popen(['task'] + cmd.split(), stdout=PIPE, stderr=PIPE)
    return tw.communicate()

def get_json(query):
    'call taskwarrior, returning objects from json'
    result, err = call_taskwarrior('end.after:today xor status:pending export %s' % query)
    return json.loads(JSON_START + result.strip().replace("\n",",") + JSON_END)

def call_dot(instr):
    'call dot, returning stdout and stdout'
    dot = Popen('dot -Tpdf'.split(), stdout=PIPE, stderr=PIPE, stdin=PIPE)
    return dot.communicate(instr.encode('utf-8'))

if __name__ == '__main__':
    query = sys.argv[1:]
    print ('Calling TaskWarrior')
    # Print data.
    data = get_json(' '.join(query))

    maxUrgency = -9999;
    for datum in data:
        if float(datum['urgency']) > maxUrgency:
            maxUrgency = float(datum['urgency'])

    # First pass: labels.
    lines = [HEADER]
    print ('Printing Labels')
    for datum in data:
        validUuids.append(datum['uuid'])
        if datum['description']:

            style = ''
            color = ''
            style = 'filled'

            if datum['status']=='pending':
                prefix = datum['id']
                if not datum.get('depends','') : color = unblockedColor
                else :
                    hasPendingDeps = 0
                    for depend in datum['depends'].split(','):
                        for datum2 in data:
                            if datum2['uuid'] == depend and datum2['status'] == 'pending':
                               hasPendingDeps = 1
                    if hasPendingDeps == 1 : color = blockedColor
                    else : color = unblockedColor

            elif datum['status'] == 'waiting':
                prefix = 'WAIT'
                color = waitColor
            elif datum['status'] == 'completed':
                prefix = 'DONE'
                color = doneColor
            elif datum['status'] == 'deleted':
                prefix = 'DELETED'
                color = deletedColor
            else:
                prefix = ''
                color = 'white'

            if float(datum['urgency']) == maxUrgency:
                color = maxUrgencyColor

            label = '';
            descriptionLines = textwrap.wrap(datum['description'],charsPerLine);
            for descLine in descriptionLines:
                label += descLine+"\\n";

            # Documentation http://www.graphviz.org/doc/info/attrs.html
            lines.append('"%s"[shape=box][penwidth=%d][label="%s\:%s"][fillcolor=%s][style=%s]' % (datum['uuid'], penWidth, prefix, label, color, style))

    # Second pass: dependencies.
    print ('Resolving Dependencies')
    for datum in data:
        if datum['description']:
            for dep in datum.get('depends', '').split(','):
                #print ("\naaa %s" %dep)
                if dep!='' and dep in validUuids:
                    lines.append('"%s" -> "%s"[dir=%s];' % (dep, datum['uuid'], dir))
                    continue

    # Third pass: projects.
    print ('Making and Linking Project Nodes')
    for datum in data:
        for proj in datum.get('project', '').split(','):
            if proj != '':
                lines.append('"%s" -> "%s"[dir=both][arrowtail=odot];' % (proj, datum['uuid']))
                lines.append('"%s"[shape=circle][fontsize=40.0][penwidth=16][color=gray52]' % (proj))
                continue

    # Third pass: tags.
    print ('Making and Linking Tag Nodes')
    for datum in data:
        for tag in datum.get('tags',''):
            if tag != '':
                lines.append('"%s" -> "%s";' % (datum['uuid'], tag))
                lines.append('"%s"[shape=square][fontsize=24.0][penwidth=8]' % (tag))
                continue

    lines.append(FOOTER)

    print ('Calling dot')
    pdf, err = call_dot('\n'.join(lines))
    if err != '':
        print ('Error calling dot:')
        print (err.strip())

    fd, tmpname = mkstemp('.pdf', 'taskgv-')
    print ('Writing to %s' % tmpname)
    with fdopen(fd, 'w') as f:
        f.write(pdf)

# Use `xdg-open` if it's present, `open` otherwise.
display_command = spawn.find_executable("xdg-open")
if display_command == None:
    display_command = spawn.find_executable("open")

subprocess.call([display_command, tmpname])
