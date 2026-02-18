#include <GUIConstantsEx.au3>
#include <WindowsConstants.au3>
#include <EditConstants.au3>
#include <MsgBoxConstants.au3>
#include <FileConstants.au3>

; --- Config ---
Global Const $DEFAULT_SAVE = @DesktopDir & "\altiplan.json"
Global Const $DEFAULT_MONTHS = 30
Global Const $exePath = @ScriptDir & "\altiplan.exe" ; altiplan.exe i samme folder som .au3

; --- GUI ---
Global $hGUI = GUICreate("altiplan.exe - simpel frontend", 520, 240, -1, -1, BitOR($WS_CAPTION, $WS_SYSMENU))

GUICtrlCreateLabel("Afdeling:", 20, 25, 100, 20)
Global $inpDept = GUICtrlCreateInput("", 140, 20, 340, 24)

GUICtrlCreateLabel("Brugernavn:", 20, 65, 100, 20)
Global $inpUser = GUICtrlCreateInput("", 140, 60, 340, 24)

GUICtrlCreateLabel("Kode (password):", 20, 105, 120, 20)
Global $inpPass = GUICtrlCreateInput("", 140, 100, 340, 24, $ES_PASSWORD)

GUICtrlCreateLabel("Filnavn:", 20, 145, 100, 20)
Global $inpFile = GUICtrlCreateInput($DEFAULT_SAVE, 140, 140, 260, 24)
Global $btnBrowse = GUICtrlCreateButton("Vælg...", 410, 140, 70, 24)

Global $btnRun = GUICtrlCreateButton("Kør", 140, 185, 120, 32)
Global $btnExit = GUICtrlCreateButton("Luk", 270, 185, 120, 32)

Global $lblStatus = GUICtrlCreateLabel("", 20, 220, 480, 16)

GUISetState(@SW_SHOW)

; --- Helpers ---
Func _Trim($s)
    Return StringStripWS($s, 3)
EndFunc

Func _Quote($s)
    ; Quote til cmdline (håndterer mellemrum i paths)
    Return '"' & $s & '"'
EndFunc

Func _SetStatus($txt)
    GUICtrlSetData($lblStatus, $txt)
EndFunc

; --- Loop ---
While 1
    Switch GUIGetMsg()
        Case $GUI_EVENT_CLOSE, $btnExit
            Exit

        Case $btnBrowse
            Local $picked = FileSaveDialog("Vælg outputfil", @DesktopDir, "JSON (*.json)|Alle filer (*.*)", $FD_PATHMUSTEXIST + $FD_OVERWRITEPROMPT, "altiplan.json", $hGUI)
            If Not @error And $picked <> "" Then
                GUICtrlSetData($inpFile, $picked)
            EndIf

        Case $btnRun
            Local $dept = _Trim(GUICtrlRead($inpDept))
            Local $user = _Trim(GUICtrlRead($inpUser))
            Local $pass = GUICtrlRead($inpPass) ; ikke trim password unødigt
            Local $save = _Trim(GUICtrlRead($inpFile))

            If $dept = "" Or $user = "" Or $pass = "" Or $save = "" Then
                MsgBox($MB_ICONWARNING, "Manglende felter", "Udfyld venligst Afdeling, Brugernavn, Kode og Filnavn.")
                ContinueLoop
            EndIf

            If Not FileExists($exePath) Then
                MsgBox($MB_ICONERROR, "Mangler altiplan.exe", "Kunne ikke finde:" & @CRLF & $exePath & @CRLF & @CRLF & _
                       "Læg altiplan.exe i samme mappe som dette script, eller ret $exePath i koden.")
                ContinueLoop
            EndIf

            ; Byg argumenter (quote alle værdier)
            Local $args = "--afdeling " & _Quote($dept) & _
                          " --brugernavn " & _Quote($user) & _
                          " --password " & _Quote($pass) & _
                          " --months " & $DEFAULT_MONTHS & _
                          " --savefile " & _Quote($save)

            ; Kør i "silent" konsol (ingen sort vindue): @SW_HIDE
            _SetStatus("Kører...")

            Local $rc = RunWait(_Quote($exePath) & " " & $args, @ScriptDir, @SW_HIDE)

            If $rc = 0 Then
                _SetStatus("Færdig. Output gemt: " & $save)
                MsgBox($MB_ICONINFORMATION, "Færdig", "Kørslen er færdig." & @CRLF & "Output: " & $save)
            Else
                _SetStatus("Fejl (exit code " & $rc & ").")
                MsgBox($MB_ICONERROR, "Fejl", "altiplan.exe returnerede exit code: " & $rc & @CRLF & _
                       "Tjek evt. credentials, netværk, og at stien kan skrives.")
            EndIf
    EndSwitch
WEnd
