import os
import win32api
import win32com.client

def resolve_windows_shortcut(path):
    """
    If the path is a .lnk file, returns the actual target .exe path.
    Otherwise returns the path as is.
    """
    if path.lower().endswith('.lnk'):
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(path)
            return shortcut.Targetpath
        except Exception:
            return path
    return path

def get_game_name_from_metadata(exe_path):
    """
    Attempts to read the 'ProductName' or 'FileDescription' 
    from the executable's version information.
    """
    try:
        # Get language and codepage
        info = win32api.GetFileVersionInfo(exe_path, "\\")
        lang, codepage = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")[0]
        
        # Possible keys where the clean name is stored
        keys = ["ProductName", "FileDescription"]
        for key in keys:
            str_info = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{key}"
            name = win32api.GetFileVersionInfo(exe_path, str_info)
            if name and name.strip():
                return name.strip()
    except Exception:
        pass
    
    # Fallback: Just the filename without extension
    return os.path.splitext(os.path.basename(exe_path))[0]