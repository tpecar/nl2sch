"""
Protel Netlist Parser

The Standard Protel netlist has two sections
 1. component descriptor
 2. net descriptor

The Protel 2 netlist has three sections. This format is an extension of the standard format,
with additional fields in the component description section, additional component information
in the netlist section (for simulation) and a third section that contains PCB layout directives.

----------------------------------------------------------------------
Altium Designer PCB Netlist Manager exports in Standard Protel format.
----------------------------------------------------------------------
"""

import re
from typing import Any

class NetComponent:
    def __init__(self, designator: str, footprint: str, value: str) -> None:
        self.designator = designator
        self.footprint = footprint
        self.value = value

        self.connections: dict[str, str] = {} # pin to netlist (global label) map


class Netlist:
    def __init__(
        self,

        comps       : dict[str, NetComponent],               # component designator to NetComponent map
        nets        : dict[str, list[(NetComponent, str)]]   # net to connected pin list map
    ) -> None:
        self.comps = comps
        self.nets = nets

    @classmethod
    def loadFromFile(cls, nl_file_path: str) -> Any:

        # No context managers, let it fail fast
        nl_fd = open(nl_file_path, mode='r')
        nl = nl_fd.read()
        nl_fd.close()

        # Extract NetComponents
        """
        The first section describes each component.
        Each component description is enclosed in square brackets. 

        - The first line of the description is the component designator.

        - The second line is the footprint that was assigned to that component (in the Part dialog box).
        There must be a matching component pattern in the PCB design file, which must have pin numbers
        that match the pin numbers of the component in the schematic.

        - The third line is the information in the Part Type field.
        """
        comps = {d : NetComponent(d, f, v) for d,f,v in re.findall('\[\n(.*)\n(.*)\n(.*)\n\n\n\n\]', nl)}

        # Extract nets
        # Set up net to connected pin (NetComponent, component pin) mapping
        """
        - The second section describes each net. Each net is enclosed in rounded brackets.

        - The first line is the name of the net. If the net has no net label then a name will be assigned
        during netlist creation.
        
        - The following lines show each node in the net. The component designator and pin number will
        define each node (eg. U7-3, component U7, pin 3).
        """
        nets = {
            net :
                [
                    (comps[d], pin)
                    for d, pin in
                    [conn.split('-') for conn in conns.split('\n')]
                ]
            for net, conns in re.findall('\(\n(.*)\n([\s\S]+?)\n\)', nl)
        }

        # Set up component connections (pin to net mapping) in NetComponents
        for net, conns in nets.items():
            for comp, pin in conns:
                comp.connections[pin] = net
        
        return cls(
            comps = comps,
            nets = nets
        )

if __name__ == '__main__':
    # Quick test if netlist loading works

    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'nl_path',
        help='Existing netlist in Protel format'
    )

    args = parser.parse_args(sys.argv[1:])

    nl = Netlist.loadFromFile(args.nl_path)

    # Dump out in abbreviated form
    num_2pin = 0

    for d, comp in nl.comps.items():

        if len(comp.connections) > 2:
            print(f'{d} ({comp.value}):')
            for pin, net in comp.connections.items():
                print(f'{pin:>5} {net}')
        else:
            num_2pin += 1
    
    print(f'\nAnd {num_2pin} 2-pin components.')
