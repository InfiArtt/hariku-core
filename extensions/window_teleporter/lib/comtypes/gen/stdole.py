from enum import IntFlag

import comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 as __wrapper_module__
from comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 import (
    IFont, FONTITALIC, BSTR, Picture, HRESULT, DISPPROPERTY,
    OLE_YPOS_CONTAINER, CoClass, IPictureDisp, OLE_YPOS_HIMETRIC,
    Default, Gray, OLE_YSIZE_CONTAINER, IEnumVARIANT, StdPicture,
    Checked, OLE_YPOS_PIXELS, FontEvents, OLE_COLOR,
    OLE_YSIZE_HIMETRIC, Font, Color, IUnknown, _check_version,
    OLE_XPOS_HIMETRIC, OLE_XSIZE_CONTAINER, OLE_XPOS_CONTAINER,
    OLE_CANCELBOOL, Monochrome, OLE_ENABLEDEFAULTBOOL, IPicture,
    Library, DISPPARAMS, OLE_OPTEXCLUSIVE, OLE_XSIZE_HIMETRIC,
    VgaColor, FONTSIZE, FONTSTRIKETHROUGH, FONTUNDERSCORE, IDispatch,
    FONTBOLD, OLE_XPOS_PIXELS, VARIANT_BOOL, Unchecked, StdFont,
    OLE_HANDLE, OLE_YSIZE_PIXELS, typelib_path, OLE_XSIZE_PIXELS,
    dispid, EXCEPINFO, COMMETHOD, _lcid, IFontEventsDisp, DISPMETHOD,
    GUID, IFontDisp, FONTNAME
)


class OLE_TRISTATE(IntFlag):
    Unchecked = 0
    Checked = 1
    Gray = 2


class LoadPictureConstants(IntFlag):
    Default = 0
    Monochrome = 1
    VgaColor = 2
    Color = 4


__all__ = [
    'OLE_ENABLEDEFAULTBOOL', 'IPicture', 'Library', 'IFont',
    'Picture', 'OLE_YPOS_CONTAINER', 'OLE_OPTEXCLUSIVE',
    'OLE_TRISTATE', 'IPictureDisp', 'OLE_YPOS_HIMETRIC', 'IFontDisp',
    'OLE_XSIZE_HIMETRIC', 'Default', 'VgaColor', 'Gray',
    'OLE_YSIZE_CONTAINER', 'FONTSIZE', 'FONTSTRIKETHROUGH',
    'FONTUNDERSCORE', 'OLE_XPOS_CONTAINER', 'LoadPictureConstants',
    'FONTBOLD', 'Checked', 'OLE_CANCELBOOL', 'OLE_YPOS_PIXELS',
    'OLE_XPOS_PIXELS', 'FontEvents', 'Unchecked', 'StdFont',
    'OLE_COLOR', 'OLE_HANDLE', 'OLE_YSIZE_PIXELS',
    'OLE_YSIZE_HIMETRIC', 'typelib_path', 'Font', 'OLE_XSIZE_PIXELS',
    'Monochrome', 'OLE_XPOS_HIMETRIC', 'OLE_XSIZE_CONTAINER',
    'IFontEventsDisp', 'Color', 'FONTITALIC', 'StdPicture', 'FONTNAME'
]

