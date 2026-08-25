# SkinForge - A toolset for "hammering" enigma2 skins

## Introduction
Originally an enigma2 skin was a flat xml data structure, no hierarchical includes, no macros, no relative positioning of screen elements, no high level framework, no automatic scaling... no nothing. :-)
Modern enigma2 distris like openatv and openvix add reusable panel structures and scaling, but a nice hierarchical design is still not possible.

## Motivation
So, creating skins for enigma2 was a task for someone who has killed their father and mother.
If you have a set of plugins you probably would like to have the same look and feel across all plugins. You may also want to maintain changes of skin elements only in one spot instead of having to maintain multiple instances of the same code in several plugins.

## Objective
Define an object oriented approach that sort of provides data encapsulation, inheritance, and reuse of skin elements across multiple skin screens and plugins.
The basic new concept to create hierarchical skins is a new ```<xmlinc ... />``` xml element that basically replaces ```<layout ... />``` elements and accepts parameters like position and other local or global parameter variables.

## Features
- Multi-level include files ```<xmlinc file="include_file_name" parameter_list/>```
- Global variables defined by ```<global name="var_name" value="var_value"/>``` and implicitely defined global screen vars: $screen_width, $screen_height
- Formula evaluation: eval(formula) including ternary operator (if ... else...)
- Library of skin building blocks, like buttons, titles, etc.

## Status
This project is work in progress.

## Tools:
- xmlscale
```
    xmlscale <scale> <input-file> <outpout-file>
```
- xmlmerge
```
    xmlmerge <input-file 1> <input-file 2> <outpout-file>
```
- xmlinc
```
    xmlinc <xml-source-file> <destination-dir> <common-files-dir
```
- xmlpretty (checks xml file for correctness and prettifies xml file)
```
    xmlpretty <xml-source-file/dir> <xml-destination-file/dir>
```
- xmlsplit
```
    xmlsplit <input-file>
```
- svgscale (only works on pc, as librsvg2-bin is not available on the box)
```
    svgscale <scale> <svg-file>
```
- svgscaledir (including subdirs)
```
    svgscaledir <scale> <dir>
```

## Installation
No package available, just clone the git:
"git clone git@github.com:xcentaurix/SkinForge.git"


## Examples
### Example for xmlinc with parameter(s)
main file: Example.xml

    <skin>
        <screen>
            <xmlinc file="test" source="title"/>
        </sreen>
    </skin>

include file: test.xmlinc

    <widget ... source=$source .../>

in the include file source will be replaced by the source parameter in Example.xml which results in:

    <widget ... source="title" .../>

### Example for relative xmlinc (only for position parameter)
main file: Example.xml

    <skin>
        <screen>
            <xmlinc file=buttons position="100,200"/>
        </screen>
    </skin>

include file: buttons.xmlinc

    <ePixmap pixmap="Default-FHD/skin_default/buttons/red.svg" position="0,0" size="300,70"/>
    <ePixmap pixmap="Default-FHD/skin_default/buttons/green.svg" position="300,0" size="300,70"/>
    <ePixmap pixmap="Default-FHD/skin_default/buttons/yellow.svg" position="600,0" size="300,70"/>
    <ePixmap pixmap="Default-FHD/skin_default/buttons/blue.svg" position="900,0" size="300,70"/>

The position of the red button will be: "100,200", the position of the green button will be "400,200".

## Disclaimer
The project author is not responsible for how this software is used by others. It is not intended to be used for accessing or distributing copyrighted materials without authorization.
Users are solely responsible for determining the legality of their actions.

This repository has no control over the streams, links, or the legality of the content provided by the different hosts (including all mirror sites). It is the end user's responsibility to ensure the legal use of these streams, and we strongly recommend verifying that the content complies with all applicable laws, including copyright laws and regulations of your country's jurisdiction before use.

## Limitations
- Tested on OpenViX and OpenATV with DM900.

## Links
- Installation: https://xcentaurix.github.io/SkinForge
