# Netlist to (very shitty) KiCad schematic

For when you have the PCB design / PCB netlist, but not the schematic.

The motivation for writing this tool came from the [EBAZ4205 project](https://github.com/xjtuecho/EBAZ4205) where the PCB design file was sourced, but the schematic file was missing.

Currently KiCad (or any EDA for that matter) doesn't have the capability to import netlists into schematics.

This tool aims to, at least to some degree, make this possible.

## Input format specification

Altium Designer allows export of the internal PCB netlist via the [Netlist Manager](https://www.altium.com/documentation/altium-designer/pcb-dlg-netlistmanagernetlist-manager-ad).
It exports into the Protel netlist format, the specification for which is available in the [Protel 99 SE Training Manual - Schematic Capture](./Protel_99_SE_Training_Manual__Schematic_Capture.pdf)

The alternative would be to use the pcbnew API to extract netlist information from there, but given that the Altium importer isn't complete yet, I thought it's best we try to interpret data from the source.

## Output format specification

KiCad will (eventually) have an API for eeschema, but at the time of writing isn't ready yet (and probably won't be for some time, as this feature was postponed to after v6). So the only way right now is to generate the schematic file directly.

Before KiCad v6, eeschema used its own SPICE-like format, [documented in detail here](https://kicad.org/help/legacy_file_format_documentation.pdf).

Version v6 (+ nightlies as of Q2 2020) have switched to S-expression / s-expr / sexpr LISP-like data format.
This format, at the time of writing, had no official documentation, so we need to look at the merge requests / sources

- [initial s-expression parser merge](https://gitlab.com/kicad/code/kicad/-/merge_requests/135)
- [s-expression parser](https://gitlab.com/kicad/code/kicad/-/tree/d67cf2f9afa40361bdefe195704fba881fd7c7d2/libs/sexpr)
- [eeschema load / save handler](https://gitlab.com/kicad/code/kicad/-/blob/bb232e6ac6db07919540a28b346a36e68b2f6566/eeschema/sch_plugins/kicad/sch_sexpr_plugin.cpp)

## Operation

Since KiCad doesn't reconnect pins after you change the symbol, changing the symbol after the fact would be a
royal pain in the ass.

So in order to get things right the first time:

- components matching rules (as a separate python file) are provided, by which the symbol gets assigned
  - designator, footprint, value (can be wildcard, can be specific ID - 3 separate regexes basically)
  The first rule that matches gets used (as in firewall, so most specific rules first).

    Note that footprint is usually useless - capacitors are in different sizes on the PCB, but same symbol on the sch.

  Each rule then specifies
  - eeschema s-expr template for symbol (you provide ref, val)
  - eeschema s-expr template for global labels (so that nets can be properly attached) (you provide net[pin_name].label net[pin_name].x net[pin_name].y)
    Place such symbol in eeschema, set up nets, save, see how it gets saved

    - pin_name has to match netlist pin name
    - netlist gets parsed and for each component a dict of pin names to its connected nets is made

    the ref, val, net are variables provided by the engine, your string will be treated as an f-string and eval()-ed
  - bounding box (with labels included) - this is so that the engine can place symbols without overlapping
    It also allows us to do various vertical / horizontal packing of symbols in the future.

- if there is no match, we report an error - you check the symbol, you make the rule that matches it and let it go its merry way again
  - there is also an "skip-missing" option for it to continue when no rule matches - the component is dropped
    Intended for testing so that you at least get something.

## Usage

The tool has no dependencies besides a standard Python 3 installation.

The tool was developed with KiCad Version: (5.99.0-8214-g099ddb1517), release build

```
./nl2sch.py ./ebaz4205/ebit_ad.Net ./ebaz4205/components/ ./ebaz4205/ebaz4205.kicad_sch --allow-missing-components --allow-missing-pins
```

For viewing/editing the generated schematic, the following can help:

- apply the blank.kicad_wks Page layout description file (Under File > Page Settings)
- add a new sheet / standalone schematic and start moving symbols there (current nightly has support for cut-paste while keeping annotations)
  
  [Possibly even hack the control](https://gitlab.com/kicad/code/kicad/-/blob/77f65163/eeschema/tools/sch_editor_control.cpp#L1381) so that it doesn't bring up that pointless dialog + bind Ctrl+V t it.

## License

[MIT License](./LICENSE.md)

Do whatever you want with it, don't blame me if/when it doesn't work.
