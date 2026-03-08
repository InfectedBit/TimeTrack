' TimeTrack — Lanzador silencioso (SIN ventana de consola)
' Ideal para accesos directos, inicio con Windows, etc.
' Usa pythonw.exe que suprime la consola completamente.

Option Explicit

Dim fso, baseDir, pythonw, script, shell

Set fso     = CreateObject("Scripting.FileSystemObject")
baseDir     = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw     = baseDir & "\.venv\Scripts\pythonw.exe"
script      = baseDir & "\tray.py"

' Verificar que el venv existe
If Not fso.FileExists(pythonw) Then
    MsgBox "No se encuentra el entorno virtual." & vbCrLf & vbCrLf & _
           "Ejecuta primero setup.bat para instalar las dependencias.", _
           vbCritical, "TimeTrack — Error"
    WScript.Quit 1
End If

' Lanzar sin ventana (0 = oculta, False = no esperar)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = baseDir
shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
