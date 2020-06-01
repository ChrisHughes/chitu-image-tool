# chitu-image-tool
Command line tool to decode and encode image assets in Chitu 3D printer firmware, used in Tronxy, and other printers with a color graphical touch screen.

This tool lets you change the start-up screen, and the graphics used in the printer's user-interface.

![Example boot screen](example.jpg?raw=true "Example of customized boot screen")

## Installation

Requires Python 3, PIP and the following package:

`
pip install Pillow 
`

## Disclaimer

Use this at your own risk. I am not responsible if you brick or damage your printer. Have a copy of your manufacturer's latest firmware on hand in case you break something.

Latest firmware for Tronxy X5SA line of printers is available [here](https://www.thingiverse.com/groups/tronxy/forums/general/topic:33023#comment-3436737).

## Usage

chitu-image-tool.py *action* *file*

Actions include encode, decode, encode_package, decode_package.

Encode and decode operate on single-image files (.logo), these contain start-up screens.

Encode_package and decode_package operate on bundled assets (.bin), these contain UI image catalogs.

To flash your printer, load a .logo or .bin file onto your SD card, go to the print menu and select the file and hit print. Changes will be fully applied after you restart your printer.

### Encode single image

chitu-image-tool.py encode *&lt;path to image&gt;* *&lt;path to output&gt;*

Options:  
-W, --width - will resize image if included  
-H, --height - will resize image if included  
-t, --tag - will change numerical tag that firmware uses to identify image. This distinguishes where the image will be used. By default the tag is set to 0x12FD000B which is used as boot screen in most FW's.  

### Decode single image

chitu-image-tool.py decode *&lt;path to .logo file>*

Options:  
-s, --show - Displays the decoded image in a new window  
-o, --output *&lt;filename&gt;* - Save outputted image to file.  
-W, --width - Width of image (i.e. pixel width of printer's LCD)  
-H, --height - Height of image (i.e. pixel height of printer's LCD)  

### Encode Package

chitu-image-tool.py encode_package *&lt;path to catalog folder&gt;*

Options:  
-t TAG, --tag TAG - Specify 4 byte catalog tag. Defaults to name of folder if omitted.  

Note: Only flash complete UI packages containing all images from manufacturer's original firmware, at their original sizes. Tag information to identify package images is contained in the filenames of these images, these are used to re-encode an identical package.

### Decode Package

chitu-image-tool.py decode_package *&lt;path to .bin package&gt;*

Options:  
-t TAGS, --tags TAGS - Specify comma separated list of tags to decode. Decodes all by default.



