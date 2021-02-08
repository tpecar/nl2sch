#!/usr/bin/env python3
"""
Generate footprint library from KiCad v6 pcb symbols + associate them.
"""

import sys
import argparse
import os
import re

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'src_pcb',
        help='Source KiCad PCB'
    )
    parser.add_argument(
        'target_pcb',
        help='Target KiCad PCB which will have footprints associated to generated lib'
    )
    parser.add_argument(
        'lib_path',
        help='Generated library folder path'
    )

    args = parser.parse_args(sys.argv[1:])

    # Get target folder name (library name) from path
    lib_name = os.path.basename(args.lib_path).split('.')[0]

    # Number of footprint instances with no reference
    # Such instances get UNKNOWN_xxx footprint name
    unk_count = 0

    with open(args.src_pcb) as src_pcb:
        src_pcb = src_pcb.read()

        # "Replace" lambda that generates a footprint library entry (.kicad_mod file)
        # and returns pcb footprint instance that is associated with the generated entry
        def fp_lib_gen(match):
            global unk_count

            fp = match.group(0)

            ref = re.search('\(fp_text reference "([^"]*)"', fp).group(1)

            if not ref:
                # No reference
                ref = f'UNKNOWN_{unk_count}'
                unk_count += 1

            fp_path = f'{args.lib_path}/{ref}.kicad_mod'
            print(fp_path)

            with open(fp_path, 'w') as outfile:
                outfile.write(fp)
            
            # Reassociate all footprints (even if they are already associated to a lib)
            # to our generated lib
            return re.sub('  \(footprint "[^"]*"', f'  (footprint "{lib_name}:{ref}"', fp)

        pcb = re.sub('  \(footprint [\s\S]+?(?:\n  \))', fp_lib_gen, src_pcb)

        print(args.target_pcb)
        with open(args.target_pcb, 'w') as target_pcb:
            target_pcb.write(pcb)
