#!/usr/bin/env python3
"""
Netlist to (very shitty) KiCad schematic converter
"""

import sys
import os
import argparse
from typing import DefaultDict

from net import Netlist
from comp import MatchedSchComponent, PlacedSchComponent, SchComponent

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
        '-ac', '--allow-missing-components',
        help='Skip NetComponent with no SchComponent matches',
        action='store_true'
    )
    parser.add_argument(
        '-ap', '--allow-missing-pins',
        help='Allow SchComponents with missing pins',
        action='store_true'
    )
    parser.add_argument(
        '--width',
        help='Maximum width of a component group in schematic',
        type=int,
        default=450
    )
    parser.add_argument(
        '--spacing',
        help='Spacing between groups of components',
        type=int,
        default=10
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

    # Phase 1 - match & collect
    no_skipped = 0
    no_missing_pins = 0

    all_matched_comps : dict[SchComponent, list[MatchedSchComponent]] = DefaultDict(list)

    for net_comp in netlist.comps.values():
        net_comp_str = f'[{net_comp.designator} {net_comp.footprint} {net_comp.value}]'

        # Find first SchComponent that can match the D, F, V of net_comp
        for sch_comp in sch_comps:
            match = sch_comp.match(net_comp)
            if match:

                # Check if the matched SchComponent has all pins referenced by the netlist
                for net_pin in match.net_comp.connections.keys():
                    if net_pin not in sch_comp.label_tpls:
                        msg = (
                            f'{match.sch_comp.symbol_lib_name} ' +
                            f'is missing pin {net_pin} for instance {match.net_comp.designator}'
                        )
                        if args.allow_missing_pins:
                            print(f'WARN: {msg}')
                            no_missing_pins += 1
                        else:
                            print(f'ERROR: {msg}')
                            sys.exit(1)

                all_matched_comps[sch_comp].append(match)
                break
        else:
            # We didn't match any sch_comp
            if args.allow_missing_components:
                print(f'WARN: SKIPPING {net_comp_str}')
                no_skipped += 1
            else:
                print(f'ERROR: {net_comp_str} could not be mapped to any SchComponent')
                sys.exit(1)

    if args.allow_missing_components:
        print(f'Skipped {no_skipped} netlist components.')
    
    if args.allow_missing_pins:
        print(f'Found {no_missing_pins} missing pins.')
    
    # Phase 2 - place

    # Dump the components by descending pin count
    all_matched_comps_sorted = sorted(
        all_matched_comps.items(),
        key = lambda m : len(m[0].label_tpls),
        reverse=True
    )
    all_placed_comps : list[PlacedSchComponent] = []

    x, y = 0,0
    max_x = 0

    for sch_comp, matched_comps in all_matched_comps_sorted:
        for matched_comp in matched_comps:

            all_placed_comps.append(matched_comp.place((x,y)))

            new_x = x + sch_comp.bounds[0]
            new_y = y + sch_comp.bounds[1]

            # If the next component would be outside specified bounds,
            # we will place it in the next row
            if new_x > args.width:
                x = 0
                y = new_y
            else:
                # otherwise move within the row
                x = new_x
            
            # Expand schematic bounds, if necessary
            if new_x > max_x:
                max_x = new_x

        else:
            if x:
                # If we're currently in a non-empty row, move into new row
                y = y + sch_comp.bounds[1]
            x = 0
            y += args.spacing

    # Render placed components into KiCad schematic

    print(f'Writing schematic to {args.kicad_sch_path}')

    rendered_lib_symbol = '\n'.join([p.lib_symbol for p in all_matched_comps.keys()])

    rendered_labels = '\n'.join([p.rendered_labels for p in all_placed_comps])
    rendered_symbol = '\n'.join([p.rendered_symbol for p in all_placed_comps])
    rendered_symbol_instance = '\n'.join([p.rendered_symbol_inst for p in all_placed_comps])

    kicad_sch = open(args.kicad_sch_path, 'w')
    kicad_sch.write(
f'''
(kicad_sch (version 20201015) (generator eeschema)

  (paper "User" {max_x} {y})

  (lib_symbols
{rendered_lib_symbol}
  )

{rendered_labels}
{rendered_symbol}

  (sheet_instances
    (path "/" (page ""))
  )

  (symbol_instances
{rendered_symbol_instance}
  )
)
'''
    )
    kicad_sch.close()

    print("Done.")

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
