import os

from anki.lang import _

from .config import getUserOption

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))
js_file = os.path.join(__location__, "deckbrowser.js")
css_file = os.path.join(__location__, "defaultcss.css")

with open(js_file, "r") as f:
    js = f.read()
with open(css_file, "r") as f:
    css = f.read()


######################
#header related html #
######################
start_header = """
  <tr style = "vertical-align:text-top">"""

deck_header = f"""
    <th colspan = 5 align = left>
      {_("Deck")}
    </th>"""


def column_header(heading, colpos):
    return f"""
    <th class = "count ui-draggable ui-draggable-handle ui-droppable" colpos = "{colpos}">
      <a onclick = "return pycmd('optsColumn:{colpos}');">
        {_(heading)}
      </a>
    </th>"""


option_header = """
    <th></th>"""

option_name_header = """
    <td></td>"""

end_header = """
  </tr>"""


##############
#deck's html #
##############
def start_line(klass, did):
    return f"""
  <tr class = '{klass}' id = '{did}'>"""


def collapse_children_html(did, name, prefix):
    return f"""
      <a class = collapse onclick = 'return pycmd("collapse:{did}")' id = "{name}" href = "#{name}" >
         {prefix}
      </a>"""


collapse_no_child = """
      <span class = collapse></span>"""


def deck_name(depth, collapse, extraclass, did, cssStyle, name):
    padding = f" style = 'padding-left:{depth * 18}px'" if depth else ""
    return f"""
      <div class = ios-row-left{padding}>
        <div class = ios-collapse-wrapper>
          {collapse}
        </div>
        <a class = "deck{extraclass} ios-row-name" href="#" onclick = "return pycmd('open:{did}')">
          <span class = "ios-row-name-text" style = '{cssStyle}'>
            {name}
          </span>
        </a>
      </div>
"""


def number_cell(colour, number, description, label):
    tooltip = ""
    klasses = ["ios-count"]
    if description:
        tooltip = f"""
      <span class = "tooltiptext">
        {description}
      </span>"""
        klasses.append("tooltip")
    stripped = str(number).strip()
    if stripped in ["0", "0%", ""]:
        klasses.append("ios-count-zero")
    label_html = ""
    if label:
        label_html = f"""
      <span class = "ios-count-label">{label}</span>"""
    return f"""
    <div class = "{" ".join(klasses)}">
      <span class = "ios-count-value" style = "color:{colour}">
        {number}
      </span>{label_html}{tooltip}
    </div>"""


def gear(did):
    return f"""
      <button class = ios-gear-btn type = button onclick = "return pycmd('opts:{int(did)}');">
        &#9881;
      </button>
"""


def deck_option_name(option):
    return f"""
      <span class = ios-option-name>
        {option}
      </span>"""


end_line = """
  </tr>"""


def bar(name, width, left, color, overlay):
    return f"""
          <div class="tooltip bar" style="position:absolute; height:100%; width:{width}%; background-color:{color}; left :{left}% ;">
            <!-- {name}-->
            <span class="tooltiptext">
              {overlay}
            </span>
          </div>"""


def progress(content):
    return f"""
      <div class="progress" style="position:relative;	height:1em;	display:inline-block;	width:100px;		">{content}
      </div>"""
