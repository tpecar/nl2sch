# Altium to Kicad conversion toolkit

The motivation for writing these tools came from the [EBAZ4205 project](https://github.com/xjtuecho/EBAZ4205) where the original Protel PCB design file was sourced.

In order to make the board approachable to the whole community, it was migrated to KiCad v6 (at the time of writing it wasn't finalized, so nightlies were used) which introduced the Altium PCB import functionality.

However, since the schematic and library files were missing, they had to be recreated from scratch - these tools automate some of the process.

## Netlist to KiCad schematic conversion tool

Uses the internal PCB netlist to place, reference and connect schematic components, creating a schematic which generates an equivalent netlist.

The components still need to be organized by the user - this can be partially aided by the tool by providing a list on how to group components.

### Input format specification

Altium Designer allows export of the internal PCB netlist via the [Netlist Manager](https://www.altium.com/documentation/altium-designer/pcb-dlg-netlistmanagernetlist-manager-ad).
It exports into the Protel netlist format, the specification for which is available in the [Protel 99 SE Training Manual - Schematic Capture](http://dtv.mcot.net/data/manual/book1155396404.pdf)

The alternative would be to use the pcbnew API to extract netlist information from there, but given that the Altium importer isn't complete yet, I thought it's best we try to interpret data from the source.

### Output format specification

KiCad will (eventually) have an API for eeschema, but at the time of writing isn't ready yet (and probably won't be for some time, as this feature was postponed to after v6). So the only way right now is to generate the schematic file directly.

Before KiCad v6, eeschema used its own SPICE-like format, [documented in detail here](https://kicad.org/help/legacy_file_format_documentation.pdf).

Version v6 (+ nightlies as of Q2 2020) have switched to S-expression / s-expr / sexpr LISP-like data format.
This format, at the time of writing, had no official documentation, so we need to look at the merge requests / sources

- [initial s-expression parser merge](https://gitlab.com/kicad/code/kicad/-/merge_requests/135)
- [s-expression parser](https://gitlab.com/kicad/code/kicad/-/tree/d67cf2f9afa40361bdefe195704fba881fd7c7d2/libs/sexpr)
- [eeschema load / save handler](https://gitlab.com/kicad/code/kicad/-/blob/bb232e6ac6db07919540a28b346a36e68b2f6566/eeschema/sch_plugins/kicad/sch_sexpr_plugin.cpp)

### Operation

This is a development log, but it should give you a general idea

>- for each symbol that can be generated you provide a separate kicad schematic, which contains
>
>  - components matching rules, by which the symbol gets assigned - designator, footprint, value (can be wildcard, can be specific ID - 3 separate regexes basically)
>  The first rule that matches gets used (as in firewall, so most specific rules first).
>
>    Note that footprint is usually useless - capacitors are in different sizes on the PCB, but same symbol on the sch.
>
>  - the placed component + labels, from which we create
>  
>    - eeschema s-expr template for symbol
>    - eeschema s-expr template for global labels (so that nets can be properly attached)
>
>      - pin_name has to match netlist pin name
>      - netlist gets parsed and for each component a dict of pin names to its connected nets is made
>
>  - bounding box (with labels included) - this is so that the engine can place symbols without overlapping
>    It also allows us to do various vertical / horizontal packing of symbols in the future.
>
>- if there is no match, we report an error - you check the symbol, you make the rule that matches it and let it go its merry way again
>  - there is also a "skip-missing" option for it to continue when no rule matches - the component is dropped
>    Intended for testing so that you at least get something.

### Usage

This tool was developed for `KiCad Version: (5.99.0-8214-g099ddb1517), release build`

Python 3.9+ is required due to [PEP 585](https://www.python.org/dev/peps/pep-0585/). It can be worked around to Python 3.7+ if required.

And while the base functionality works without dependencies, the tool relies on [pyexcel](https://pypi.org/project/pyexcel/) for XLS/ODS component group file reading.

[Pipfile](https://docs.python-guide.org/dev/virtualenvs/) was provided and can be used to set up the virtualenv
```
pipenv install
pipenv shell

./nl2sch.py ./ebaz4205/ebit_ad.Net ./ebaz4205/components/ ./ebaz4205/ebaz4205.kicad_sch --component-grouping ./ebaz4205/EBAZ4205_Kicad_recreation_effort__2021_01_24.ods --allow-missing-components --allow-missing-pins
```

Check the files in the [./ebaz4205](./ebaz4205/) directory to get an idea on how to prepare schematic components.

For viewing/editing the generated schematic, the following can help:

- apply the blank.kicad_wks Page layout description file (Under File > Page Settings)
- add a new sheet / standalone schematic and start moving symbols there (current nightly has support for cut-paste while keeping annotations)
  
  [Possibly even hack the control](https://gitlab.com/kicad/code/kicad/-/blob/77f65163/eeschema/tools/sch_editor_control.cpp#L1381) so that it doesn't bring up that pointless dialog and bind it to Ctrl+V.

## Footprint library generation & association tool

Extracts internal footprints from the PCB and create a footprint library. Associates the PCB footprint instances with library footprints.

### Operation

This is a development log, but it should give you a general idea

> Do a script that both extracts + binds to created footprint
> (needs to do both so that the map for unreferenced - UNKNOWN - footprint can be made)
> 
> should be semi trivial to do
> 
> Do everything in a search & replace lambda - find reference, update footprint entry to 
>  (footprint "ebaz4205:R248" (layer "F.Cu")
>
> ebaz4205 being the name of the library we are creating, R248 being the reference
> 
> parameters should be
> - original pcb
> - target pcb
> - target footprint lib

### Usage

This tool was developed for `KiCad Version: (5.99.0-8214-g099ddb1517), release build`

A standard Python 3 installation is required.

```
fplib.py ./ebaz4205/ebaz4205.kicad_pcb ./ebaz4205/ebaz4205_assoc.kicad_pcb ./ebaz4205/ebaz4205.pretty
```

You can use the pcbnew Tools > Update schematic from PCB to sync the footprint associations to the schematic.

## License

[MIT License](./LICENSE.md)

Do whatever you want with it, don't blame me if/when it doesn't work.
