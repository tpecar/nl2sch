#!/usr/bin/env python3
"""
Netlist to (very shitty) KiCad schematic converter
"""

import sys
import os
import argparse
from typing import DefaultDict

from net import Netlist
from comp import PlacedSchComponent, SchComponent

# Empty schematic
"""
(kicad_sch (version 20201015) (generator eeschema)

  (paper "A4")

  (lib_symbols
  )


  (sheet_instances
    (path "/" (page ""))
  )

  (symbol_instances
  )
)
"""

def main(arguments):

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'netlist_path',
        help='Existing Protel netlist file'
    )
    parser.add_argument(
        'component_root',
        help='SchComponent root'
    )
    parser.add_argument(
        'kicad_sch_path',
        help='Target Kicad (v5.99 / v6) schematic file'
    )
    parser.add_argument(
        '-s', '--skip-missing',
        help='Skip NetComponent with no SchComponent matches',
        action='store_true'
    )

    args = parser.parse_args(arguments)

    # Load netlist (get NetComponents)
    netlist : Netlist = Netlist.loadFromFile(args.netlist_path)
    print(f'Netlist parsed, {len(netlist.comps)} components, {len(netlist.nets)} nets')

    # Load SchComponents
    comp_files = sorted([
        os.path.join(dirpath, file)
        for dirpath, dirname, files in os.walk(args.component_root)
        for file in files if file.endswith('.kicad_sch')
    ])
    print(f'Found {len(comp_files)} SchComponents, parsing...')
    sch_comps : list[SchComponent] = []
    for comp_file in comp_files:
        print(f'  {comp_file} : ', end='')
        try:
            comp = SchComponent.loadFromFile(comp_file)
            print(comp)
            sch_comps.append(comp)
        except Exception as e:
            print('FAILED\n')
            raise e

    # TODO - do a simple placing algorithm that groups components based on common nets
    #        (select a central component, and the algo places everything around it)

    # Currently we just dump the components by descending pin count
    net_comps = sorted(netlist.comps.values(), key = lambda c : len(c.connections), reverse=True)

    # Last x, y for new SchComponents
    last_x, last_y = 0,0
    # Schematic bounds
    max_x, max_y = 0,0

    placed_comps: dict[SchComponent : list[PlacedSchComponent]] = DefaultDict(list)

    for net_comp in net_comps:
        net_comp_str = f'[{net_comp.designator} {net_comp.footprint} {net_comp.value}]'

        # Find first SchComponent that can match the D, F, V of net_comp
        for sch_comp in sch_comps:
            if(sch_comp.match(net_comp.designator, net_comp.footprint, net_comp.value)):
                
                placed_comps_grp: list[PlacedSchComponent] = placed_comps[sch_comp]

                # If we matched this SchComponent group before, place it in the same row
                #
                # TODO: KiCad doesn't like big schematics, so implement spilling of same group components
                #       into next row - this means though that we first need to collect the components,
                #       determine the bounds of the whole group, and _then_ place them
                #
                #       Phase 1 - detect & collect
                #       Phase 2 - place
                #
                if placed_comps_grp:
                    place_x = placed_comps_grp[-1].x + placed_comps_grp[-1].bounds[0]
                    place_y = placed_comps_grp[-1].y

                # Otherwise, start new row
                else:
                    place_x = last_x
                    place_y = last_y

                    # Advance last x, y for new category
                    last_y += sch_comp.bounds[1]

                if place_x > max_x:
                    max_x = place_x
                
                if place_y > max_y:
                    max_y = place_y

                placed_comp = sch_comp.place(place_x, place_y, net_comp.designator, net_comp.value, net_comp.connections)
                placed_comps_grp.append(placed_comp)

                print(f'PLACED {net_comp_str} as\n{placed_comp}\n')
                
                break
        else:
            # We didn't match any sch_comp
            if args.skip_missing:
                print(f'SKIPPING {net_comp_str}')
            else:
                print(f'ERROR: {net_comp_str} could not be mapped to any SchComponent')
                sys.exit(1)

    # Render placed components into KiCad schematic
    all_placed = [pc for pc_list in placed_comps.values() for pc in pc_list]

    lib_symbol = '\n'.join([p.lib_symbol for p in all_placed])
    labels = '\n'.join([p.labels for p in all_placed])
    symbol = '\n'.join([p.symbol for p in all_placed])
    symbol_instance = '\n'.join([p.symbol_instance for p in all_placed])

    kicad_sch = open(args.kicad_sch_path, 'w')
    kicad_sch.write(
f'''
(kicad_sch (version 20201015) (generator eeschema)

  (paper "User" {max_x} {max_y})

  (lib_symbols
{lib_symbol}
  )

{labels}
{symbol}

  (sheet_instances
    (path "/" (page ""))
  )

  (symbol_instances
{symbol_instance}
  )
)
'''
    )
    kicad_sch.close()

    print("Done.")

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
