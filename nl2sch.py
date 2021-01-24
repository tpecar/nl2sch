#!/usr/bin/env python3
"""
Netlist to (very shitty) KiCad schematic converter
"""

from collections import defaultdict
import sys
import os
import argparse
from typing import DefaultDict

from net import Netlist
from comp import MatchedSchComponent, Text, PlacedSchComponent, SchComponent

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
        help='SchComponent root, will be recursively scanned for .kicad_sch describing SchComponents'
    )
    parser.add_argument(
        'kicad_sch_path',
        help='Target Kicad (v5.99 / v6) schematic file'
    )
    parser.add_argument(
        '-cg', '--component-grouping',
        help='XLS/ODS file that provides lists of netlist components to group together (to split schematic into sections)',
        default=None
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
        default=7
    )

    args = parser.parse_args(arguments)

    # Load netlist (get NetComponents)
    netlist : Netlist = Netlist.loadFromFile(args.netlist_path)
    print(f'Netlist parsed, {len(netlist.comps)} components, {len(netlist.nets)} nets')

    # Load netlist grouping, if available
    net_comp_grouping = {}
    net_comp_grouping_order = []

    if args.component_grouping:
        import pyexcel
        net_comp_grouping_list = pyexcel.get_book(file_name=args.component_grouping).to_dict()

        # Ignore Info sheet, if it exists
        if net_comp_grouping_list.get('Info', None):
            del net_comp_grouping_list['Info']
        
        # Get order of groups, we will use same order for dumping into schematic
        net_comp_grouping_order = list(net_comp_grouping_list.keys())

        # Create net component designator -> group map
        net_comp_grouping_list = [
            tuple_list_item
            for tuple_list in
            [
                [(net_comp_d[0], group) for net_comp_d in net_comp_list if len(net_comp_d[0])]
                for group, net_comp_list in net_comp_grouping_list.items()
            ]
            for tuple_list_item in tuple_list
        ]

        # We could just pass the list to the dict constructor but
        # do a sanity check if there are any duplicates between sheets
        for net_comp_grouping_comp in net_comp_grouping_list:
            if net_comp_grouping_comp[0] in net_comp_grouping:
                print(f'ERROR: component {net_comp_grouping_comp} was already defined in {net_comp_grouping[net_comp_grouping_comp[0]]}')
                sys.exit(1)
            net_comp_grouping[net_comp_grouping_comp[0]] = net_comp_grouping_comp[1]

    
    # Split netlist components into groups based on net_comp_grouping
    unknown_key = 'Unknown / Unsorted'

    net_comps_grouped = DefaultDict(list)
    for net_comp_d, net_comp in netlist.comps.items():
        net_comps_grouped[net_comp_grouping.get(net_comp_d, unknown_key)].append(net_comp)

    if unknown_key in net_comps_grouped:
        net_comp_grouping_order.append(unknown_key)

    # Load SchComponents
    sch_comp_files = sorted([
        os.path.join(dirpath, file)
        for dirpath, dirname, files in os.walk(args.component_root)
        for file in files if file.endswith('.kicad_sch')
    ])
    print(f'Found {len(sch_comp_files)} SchComponents, parsing...')
    sch_comps : list[SchComponent] = []
    for sch_comp_file in sch_comp_files:
        print(f'  {sch_comp_file} : ', end='')
        try:
            comp = SchComponent.loadFromFile(sch_comp_file)
            print(comp)
            sch_comps.append(comp)
        except Exception as e:
            print('FAILED\n')
            raise e


    # Phase 1 - match & collect
    no_skipped = 0
    no_missing_pins = 0

    # Map of netlist component group / schematic section ->
    #   (Map of schematic component template -> netlist component instances)
    #
    # TODO - possibly rework the data structures
    #
    used_symbols : set[SchComponent] = set()
    all_matched_comps : dict[str, dict[SchComponent, list[MatchedSchComponent]]] = {}

    for group_name, net_comps in net_comps_grouped.items():
        group = all_matched_comps[group_name] = DefaultDict(list)
        
        for net_comp in net_comps:
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

                    used_symbols.add(sch_comp)
                    group[sch_comp].append(match)
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
    
    all_placed_comps : list[PlacedSchComponent] = []

    x, y = 0,0
    max_x = 0

    # Dump the groups in order specified in component_grouping
    for group_name in net_comp_grouping_order:

        # Place text describing the group
        x = 0
        all_placed_comps.append(Text(group_name).place((x,y)))
        y += args.spacing

        # Dump the components by descending pin count
        group_comps = sorted(
            all_matched_comps[group_name].items(),
            key = lambda m : len(m[0].label_tpls),
            reverse=True
        )
        for sch_comp, matched_comps in group_comps:
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
        else:
            # Spacing between groups
            y += args.spacing*2

    # Render placed components into KiCad schematic

    print(f'Writing schematic to {args.kicad_sch_path}')

    rendered_lib_symbol = '\n'.join([p.lib_symbol for p in used_symbols])

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
