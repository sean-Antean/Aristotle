' Runs a batch file completely hidden (no console window flash).
' Usage (from Task Scheduler):  wscript.exe run_hidden.vbs "C:\path\to\some.bat"
' The batch still runs normally and its own ">> log" redirects are preserved.
Set sh = CreateObject("WScript.Shell")
sh.Run """" & WScript.Arguments(0) & """", 0, False
