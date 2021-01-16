"""
Class describing schematic symbol.
Used in rules.py
"""

from dataclasses import dataclass
from net import NetComponent
import re
from typing import Any
import uuid

class SchComponent:
    """
    Netlist / Schematic component

    Provides rules to match netlist components and s-expr templates
    to create + connect them in the schematic.
    """

    def __init__(
        self,

        rule            : tuple[str, str, str], # Component matching rules (Designator, Footprint, Value)
            # The D,F,V rules (regex expressions) must all match for the component to be chosen
            # We use the first component that matches (more specific rule should be supplied first)
            # If no component matches, (and 'ignore-missing' is not specified) we throw an error

        lib_symbol      : str,                  # lib_symbol entry format template for component
            # Defines the graphical representation in the schematic - KiCad imports this definition from the
            # library. It also contains default designator, value, which are overridden in symbol entry.
            #
            # There may be multiple symbol instances - they all refer to the same lib_symbol (via lib_id).
            # lib_symbol is specified only once.

        label_tpls       : dict[str, str],      # pin name to format template for global label
            # Each pin will have a global label connected, we will set the label to netlist's net
            # If the netlist doesn't connect the pin, label creation will be skipped

        symbol_tpls      : dict[str, str],      # uuid to symbol entry format template for component
            # Symbol.
            # Usually one symbol per component, but multi-unit components have multiple symbols
            # for one component instance.
            # Specifies position + default D, F, V (overriden by symbol instance)

        symbol_inst_tpls : dict[str, str],      # uuid to symbol_instances entry
            # Symbol instance.

        bounds          : tuple[float, float]   # bounding box for component with labels
            # The engine will advance the global position (at which the current component is placed)
            # based on these bounds

    ) -> None:
        super().__init__()

        # Parameters specified by user
        self.designator, self.footprint, self.value = [re.compile(r) for r in rule]
        
        self.lib_symbol = lib_symbol
        self.label_tpls = label_tpls
        self.symbol_tpls = symbol_tpls
        self.symbol_inst_tpls = symbol_inst_tpls
        self.bounds = bounds

    def match(self, net_comp: NetComponent):
        if (
            self.designator.match(net_comp.designator) and
            self.footprint.match(net_comp.footprint) and
            self.value.match(net_comp.value)
        ):
            return MatchedSchComponent(self, net_comp)
        else:
            return None
    
    def __str__(self):
        # Quick and dirty description of the object
        symbol_lib_name = re.findall('\(symbol \"([^"]*)" ', self.lib_symbol)
        return f'{symbol_lib_name} Rules [Designator "{self.designator.pattern}" Footprint "{self.footprint.pattern}" Value "{self.value.pattern}"] Bounds {self.bounds}'

    @classmethod
    def loadFromFile(cls, sch_file_path : str) -> Any:
        """
        Extracts component information from a specifically crafted
        KiCad schematic and creates a SchComponent instance.

        This was developed and tested on KiCad Version: (5.99.0-8214-g099ddb1517), release build

        No guarantees given that this will work against any versions prior or after.
        """

        # No context managers, let it fail fast
        sch_fd = open(sch_file_path, mode='r')
        sch = sch_fd.read()
        sch_fd.close()

        # Extract component matching rules (Designator, Footprint, Value)
        rule = re.findall('\n  \(text "([^"]*)"[\s\S]+?(?:\n  \))', sch)
        if not rule or len(rule) > 1:
            raise Exception(f'Expected one rules instance, found {len(rule)}')
        rule = re.findall('D\s*(.+?)\\\\nF\s(.+?)\\\\nV (.+)', rule[0].replace('\\\\', '\\'))[0]
        

        # Extract lib_symbols entries
        # We expect one component here (can be multi-unit)
        lib_symbol = re.search('\(lib_symbols\n(    [\s\S]+?)(?:\n  \))', sch).group(1)

        # Extract labels, will be used as a template
        labels = re.findall('\n(  \(global_label[\s\S]+?(?:\n  \)))', sch)
        label_tpls = {re.search('global_label "(\S+)"', label).group(1) : label for label in labels}

        # Extract symbol(s), will be used as a template
        # Allow for multiple symbols in case of multi-unit components
        symbol_tpls = re.findall('\n(  \(symbol [\s\S]+?(?:\n  \)))', sch)
        if not symbol_tpls:
            raise Exception(f'No symbol found')
        # Use symbol uuid it as key
        symbol_tpls = {
            re.search('\(uuid \"([^"]*)\"\)', symbol).group(1) : symbol
            for symbol in symbol_tpls
        }

        # Extract symbol_instances entry(ies), will be used as a template
        symbol_inst_tpls = re.search('\(symbol_instances\n(    [\s\S]+?)(?:\n  \))', sch).group(1)
        symbol_inst_tpls = re.findall('(    \(path [\s\S]+?(?:\n    \)))', symbol_inst_tpls)
        # Use path uuid as key (note the slash)
        symbol_inst_tpls = {
            re.search('\(path \"\/([^"]*)\"', symbol_inst).group(1) : symbol_inst
            for symbol_inst in symbol_inst_tpls
        }

        # Sanity check that we got all symbols / instances
        # Should pass unless the schematic is malformed / regexes failed
        for uuid in symbol_tpls.keys():
            if uuid not in symbol_inst_tpls:
                raise Exception(f'Internal: symbol uuid {uuid} missing in symbol_insts')

        for uuid in symbol_inst_tpls.keys():
            if uuid not in symbol_tpls:
                raise Exception(f'Internal: symbol_insts uuid {uuid} missing in symbol')

        # Extract bounds
        # Find bounding box vertex coordinates, select max x,y (bottom right corner)
        # We assume the top left corner is at (0,0)
        bounding_box = re.findall('\n  \(polyline \(pts \(xy [\d.]+ [\d.]+\) \(xy ([\d.]+) ([\d.]+)\)\)', sch)
        if len(bounding_box) != 4:
            raise Exception(f'Expected bounding box')
        bounds = max([(float(x), float(y)) for x,y in bounding_box])


        return cls(
            rule = rule,
            lib_symbol = lib_symbol,
            label_tpls = label_tpls,
            symbol_tpls = symbol_tpls,
            symbol_inst_tpls = symbol_inst_tpls,
            bounds = bounds
        )

@dataclass
class MatchedSchComponent:

    sch_comp : SchComponent  # SchComponent (template) which matched
    net_comp : NetComponent  # NetComponent (instance) which matched

    def place(self, pos: tuple[float, float]):
        """
        Place component (translate, set designator + value, set labels to nets)
        """
        
        # The component symbol instances (which we assume were placed relative to (0,0))
        # are translated by (x, y).
        pos_re = re.compile('\(at\s+(\S+)\s+(\S+)')
        def move(match):
            return f'(at {float(match.group(1)) + pos[0]} {float(match.group(2)) + pos[1]}'

        # The symbol entry does not contain the actual designator, value
        # (this is specified by symbol_instance) but contains the actual coordinate!
        #
        # symbol and symbol_instance are connected via uuid
        #
        # We need to generate a new, unique uuids per each place() call,
        # since the schematic can have multiple instances of the same component.
        #
        uuids = {id : uuid.uuid4() for id in self.sch_comp.symbol_tpls.keys()}

        # Label pin to actual net (specified in netlist) replacement
        label_re = re.compile('\(global_label \"[^"]*\"')

        rendered_labels = "\n".join([
            label_re.sub(f'(global_label \"{self.net_comp.connections[pin]}\"',
                pos_re.sub(move, label_tpl)
            )
            for pin, label_tpl
            in self.sch_comp.label_tpls.items()

            # We generate the label only if its pin is connected to a net
            if pin in self.net_comp.connections
        ])

        uuid_re = re.compile('\(uuid \"([^"]*)\"')
        def uuid_replace(match):
            return f'(uuid "{uuids[match.group(1)]}"'

        rendered_symbol = "\n".join([
            uuid_re.sub(uuid_replace,
                pos_re.sub(move, symbol_tpl)
            )
            for symbol_tpl
            in self.sch_comp.symbol_tpls.values()
        ])

        path_re = re.compile('\(path \"\/([^"]*)\"')
        def path_replace(match):
            return f'(path "/{uuids[match.group(1)]}"'
        
        designator_re = re.compile('\(reference \"[^"]*\"\)')
        value_re = re.compile('\(value \"[^"]*\"\)')

        rendered_symbol_inst = "\n".join([
            value_re.sub(f'(value \"{self.net_comp.value}\")',
                designator_re.sub(f'(reference \"{self.net_comp.designator}\")',
                    path_re.sub(path_replace, symbol_instance)
                )
            )
            for symbol_instance
            in self.sch_comp.symbol_inst_tpls.values()
        ])

        return PlacedSchComponent(
            self,
            rendered_labels=rendered_labels,
            rendered_symbol=rendered_symbol,
            rendered_symbol_inst=rendered_symbol_inst,
            pos=pos
        )

@dataclass
class PlacedSchComponent:
    """
    KiCad schematic component + labels,
    translated to position specified at place() invocation
    """
    match : MatchedSchComponent

    rendered_labels      : str # global label entries
    rendered_symbol      : str # symbol entry
    rendered_symbol_inst : str # symbol_instance entry

    pos: tuple[float, float]

    def __str__(self):
        # Get first line of property, for all properties, to give an idea of the structure
        return '\n'.join([
            re.search('\s+\((.*)', prop).group(0)
            for prop
            in (self.lib_symbol, self.rendered_labels, self.rendered_symbol, self.rendered_symbol_inst)
        ])


if __name__ == '__main__':
    # Quick test if import from KiCad schematic file + placement works

    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'kicad_sch_path',
        help='Existing KiCad (v5.99 / v6) schematic file'
    )
    parser.add_argument(
        'out_kicad_sch_path',
        help='Create new KiCad schematic with parsed component data',
        default=None
    )
    args = parser.parse_args(sys.argv[1:])

    sch_comp = SchComponent.loadFromFile(args.kicad_sch_path)
    print(sch_comp)

    # Create a dummy NetComponent, MatchedSchComponent
    net_comp = NetComponent(
        designator='test_designator',
        footprint='test_footprint',
        value='test_value'
    )
    matched_comp = MatchedSchComponent(
        sch_comp,
        net_comp
    )

    placed_comp = matched_comp.place((0, 0))

    # If target file is provided, recreate schematic with placed component
    # (Since the net dict is empty, no labels will be created)
    if args.out_kicad_sch_path:
        with open(args.out_kicad_sch_path, 'w') as out:
            out.write(
f'''
(kicad_sch (version 20201015) (generator eeschema)

  (paper "A4")

  (lib_symbols
{placed_comp.match.sch_comp.lib_symbol}
  )

{placed_comp.rendered_labels}
{placed_comp.rendered_symbol}

  (sheet_instances
    (path "/" (page ""))
  )

  (symbol_instances
{placed_comp.rendered_symbol_inst}
  )
)
'''
            )
