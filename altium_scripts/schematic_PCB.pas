{..............................................................................}
{ Schematic to PCB Command Server - EagilinsED Agent                          }
{ Extracts schematic data and provides PCB creation commands                   }
{ Supports: Schematic Export, PCB Creation, Auto-Place, Auto-Route            }
{..............................................................................}

Var
    ServerRunning : Boolean;
    BasePath : String;
    SilentMode : Boolean;
    CurrentAction : String;

{..............................................................................}
Function GetBasePath : String;
Var
    Project : IProject;
    ProjectPath : String;
    ScriptPath : String;
    TempPath : String;
    Doc : ISch_Document;
    SchFilePath : String;
Begin
    // PRIORITY 1: Use script directory and navigate up from altium_scripts folder
    ScriptPath := GetRunningScriptProjectName;
    If ScriptPath <> '' Then
    Begin
        TempPath := ExtractFilePath(ScriptPath);
        If (TempPath <> '') And (Pos('altium_scripts', TempPath) > 0) Then
        Begin
            Result := Copy(TempPath, 1, Pos('altium_scripts', TempPath) - 1);
            If (Result <> '') And (Result[Length(Result)] <> '\') Then
                Result := Result + '\';
            If DirectoryExists(Result) And DirectoryExists(Result + 'altium_scripts\') Then
                Exit;
        End;
    End;

    // PRIORITY 2: Try to get path from current schematic document
    Doc := SchServer.GetCurrentSchDocument;
    If Doc <> Nil Then
    Begin
        SchFilePath := Doc.DocumentName;
        If SchFilePath <> '' Then
        Begin
            TempPath := ExtractFilePath(SchFilePath);
            While (TempPath <> '') And (Length(TempPath) > 3) Do
            Begin
                If DirectoryExists(TempPath + 'altium_scripts\') Then
                Begin
                    Result := TempPath;
                    If (Result <> '') And (Result[Length(Result)] <> '\') Then
                        Result := Result + '\';
                    Exit;
                End;
                TempPath := ExtractFilePath(Copy(TempPath, 1, Length(TempPath) - 1));
            End;
        End;
    End;

    // PRIORITY 3: Try to get path from current project
    Project := GetWorkspace.DM_FocusedProject;
    If Project <> Nil Then
    Begin
        ProjectPath := Project.DM_ProjectFullPath;
        If ProjectPath <> '' Then
        Begin
            Result := ExtractFilePath(ProjectPath);
            TempPath := Result;
            While (TempPath <> '') And (Length(TempPath) > 3) Do
            Begin
                If DirectoryExists(TempPath + 'altium_scripts\') Then
                Begin
                    Result := TempPath;
                    Break;
                End;
                TempPath := ExtractFilePath(Copy(TempPath, 1, Length(TempPath) - 1));
            End;
            If (Result <> '') And (Result[Length(Result)] <> '\') Then
                Result := Result + '\';
            Exit;
        End;
    End;

    // PRIORITY 4: No fallback
    Result := '';
    If (Result <> '') And (Result[Length(Result)] <> '\') Then
        Result := Result + '\';
End;

{..............................................................................}
Function GetCommandFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'altium_command.json';
End;

{..............................................................................}
Function GetResultFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'PCB_Project\altium_result.json';
End;

{..............................................................................}
Function GetSchematicInfoFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'PCB_Project\schematic_info.json';
End;

{..............................................................................}
Function GetFootprintLibrariesFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'PCB_Project\footprint_libraries.json';
End;

{..............................................................................}
Function EscapeJSONString(S : String) : String;
Var
    I : Integer;
    ResultStr : String;
Begin
    ResultStr := '';
    For I := 1 To Length(S) Do
    Begin
        If S[I] = '\' Then
            ResultStr := ResultStr + '\\'
        Else If S[I] = '"' Then
            ResultStr := ResultStr + '\"'
        Else If S[I] = #10 Then
            ResultStr := ResultStr + '\n'
        Else If S[I] = #13 Then
            ResultStr := ResultStr + '\r'
        Else If S[I] = #9 Then
            ResultStr := ResultStr + '\t'
        Else
            ResultStr := ResultStr + S[I];
    End;
    Result := ResultStr;
End;

{..............................................................................}
Function RemoveChars(S : String; CharsToRemove : String) : String;
Var
    I, J : Integer;
    ResultStr : String;
    KeepChar : Boolean;
Begin
    ResultStr := '';
    For I := 1 To Length(S) Do
    Begin
        KeepChar := True;
        For J := 1 To Length(CharsToRemove) Do
        Begin
            If S[I] = CharsToRemove[J] Then
            Begin
                KeepChar := False;
                Break;
            End;
        End;
        If KeepChar Then
            ResultStr := ResultStr + S[I];
    End;
    Result := ResultStr;
End;

{..............................................................................}
Function ReadCmd : String;
Var
    SL : TStringList;
    CmdFile : String;
    RetryCount : Integer;
    I : Integer;
Begin
    Result := '';
    CmdFile := GetCommandFile;

    If Not FileExists(CmdFile) Then Exit;
    If FileExists(CmdFile + '.tmp') Then Exit;

    RetryCount := 0;
    While RetryCount < 10 Do
    Begin
        SL := TStringList.Create;
        Try
            SL.LoadFromFile(CmdFile);
            Result := '';
            For I := 0 To SL.Count - 1 Do
                Result := Result + SL.Strings[I];
            SL.Free;

            If Length(Result) > 0 Then
                Exit;
        Except
            SL.Free;
        End;

        Sleep(100);
        Inc(RetryCount);
    End;
End;

{..............................................................................}
Procedure WriteRes(OK : Boolean; Msg : String);
Var
    F : TextFile;
    Q, TempFile, ActionStr : String;
    RetryCount : Integer;
Begin
    Q := Chr(34);
    TempFile := GetResultFile + '.tmp';

    ActionStr := CurrentAction;
    If ActionStr = '' Then ActionStr := 'unknown';

    If FileExists(TempFile) Then
    Begin
        Try
            DeleteFile(TempFile);
        Except
        End;
    End;

    RetryCount := 0;
    While RetryCount < 5 Do
    Begin
        Try
            AssignFile(F, TempFile);
            Rewrite(F);
            If OK Then
            Begin
                WriteLn(F, Chr(123) + Q + 'success' + Q + ':true,' + Q + 'message' + Q + ':' + Q + EscapeJSONString(Msg) + Q + ',' + Q + 'action' + Q + ':' + Q + ActionStr + Q + Chr(125));
            End
            Else
            Begin
                WriteLn(F, Chr(123) + Q + 'success' + Q + ':false,' + Q + 'error' + Q + ':' + Q + EscapeJSONString(Msg) + Q + ',' + Q + 'action' + Q + ':' + Q + ActionStr + Q + Chr(125));
            End;
            CloseFile(F);

            Try
                If FileExists(GetResultFile) Then DeleteFile(GetResultFile);
                RenameFile(TempFile, GetResultFile);
            Except
            End;

            Break;
        Except
            Inc(RetryCount);
            If RetryCount < 5 Then
                Sleep(300);
        End;
    End;
End;

{..............................................................................}
Procedure ClearCmd;
Var
    RetryCount : Integer;
Begin
    RetryCount := 0;
    While (RetryCount < 5) And FileExists(GetCommandFile) Do
    Begin
        Try
            DeleteFile(GetCommandFile);
        Except
            Sleep(100);
        End;
        Inc(RetryCount);
    End;
End;

{..............................................................................}
Function ParseValue(S, Key : String) : String;
Var
    I, J : Integer;
    Q : Char;
Begin
    Result := '';
    Q := Chr(34);
    I := Pos(Q + Key + Q, S);
    If I = 0 Then Exit;

    I := I + Length(Key) + 2;
    While (I <= Length(S)) And (S[I] <> ':') Do Inc(I);
    Inc(I);
    While (I <= Length(S)) And (S[I] = ' ') Do Inc(I);

    If S[I] = Q Then
    Begin
        Inc(I);
        J := I;
        While (J <= Length(S)) And (S[J] <> Q) Do Inc(J);
        Result := Copy(S, I, J - I);
    End
    Else
    Begin
        J := I;
        While (J <= Length(S)) And (S[J] <> ',') And (S[J] <> Chr(125)) Do Inc(J);
        Result := Trim(Copy(S, I, J - I));
    End;
End;

{..............................................................................}
{ EXPORT SCHEMATIC INFO                                                        }
{ Extracts components, nets, pins, power topology from the current schematic   }
{..............................................................................}
Procedure ExportSchematicInfo;
Var
    Doc : ISch_Document;
    Iterator : ISch_Iterator;
    SchComp : ISch_Component;
    SchWire : ISch_Wire;
    SchNetLabel : ISch_NetLabel;
    SchPowerObj : ISch_PowerObject;
    SchPin : ISch_Pin;
    SchJunction : ISch_Junction;
    SchSheet : ISch_SheetSymbol;
    SchNoERC : ISch_NoERC;
    PinIter : ISch_Iterator;
    ImplIter : ISch_Iterator;
    Impl : ISch_Implementation;
    Project : IProject;
    FlatDoc : IDocument;
    F : TextFile;
    Q, FinalPath, TempFilePath : String;
    CompCount, NetCount, PinCount, WireCount, PowerCount, JunctionCount : Integer;
    I, J, VCount : Integer;
    FootprintName, CompDesignator, PinName, PinDesig : String;
    CompValue, CompLibRef, CompDesc : String;
    NetObj : INet;
    NetPinObj : IPin;
    PinCompDesig, PinPinDesig : String;
Begin
    Doc := SchServer.GetCurrentSchDocument;
    If Doc = Nil Then
    Begin
        If Not SilentMode Then
            ShowMessage('Error: No schematic file is open!');
        WriteRes(False, 'No schematic open');
        Exit;
    End;

    Q := Chr(34);

    If BasePath = '' Then
        BasePath := GetBasePath;

    If Not DirectoryExists(BasePath) Then
    Begin
        If Not SilentMode Then
            ShowMessage('Path does not exist: ' + BasePath);
        WriteRes(False, 'Directory does not exist: ' + BasePath);
        Exit;
    End;

    // Ensure PCB_Project directory exists
    If Not DirectoryExists(BasePath + 'PCB_Project\') Then
    Begin
        Try
            ForceDirectories(BasePath + 'PCB_Project\');
        Except
        End;
    End;

    FinalPath := GetSchematicInfoFile;
    TempFilePath := 'C:\Windows\Temp\sch_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
    If Not DirectoryExists('C:\Windows\Temp\') Then
        TempFilePath := BasePath + 'sch_export_temp.json';

    Try
        AssignFile(F, TempFilePath);
        Rewrite(F);
    Except
        WriteRes(False, 'Cannot write to temp directory');
        Exit;
    End;

    // Start JSON
    WriteLn(F, Chr(123));
    WriteLn(F, Q + 'export_source' + Q + ':' + Q + 'altium_schematic' + Q + ',');
    WriteLn(F, Q + 'file_name' + Q + ':' + Q + EscapeJSONString(Doc.DocumentName) + Q + ',');
    WriteLn(F, Q + 'document_kind' + Q + ':' + Q + 'schematic' + Q + ',');

    // ================================================================
    // COMPONENTS
    // ================================================================
    WriteLn(F, Q + 'components' + Q + ':[');
    CompCount := 0;
    Iterator := Doc.SchIterator_Create;
    Iterator.AddFilter_ObjectSet(MkSet(eSchComponent));

    SchComp := Iterator.FirstSchObject;
    While SchComp <> Nil Do
    Begin
        If CompCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));

        CompDesignator := '';
        Try
            CompDesignator := SchComp.Designator.Text;
        Except
        End;

        CompValue := '';
        Try
            CompValue := SchComp.Comment.Text;
        Except
        End;

        CompLibRef := '';
        Try
            CompLibRef := SchComp.LibReference;
        Except
        End;

        CompDesc := '';
        Try
            CompDesc := SchComp.ComponentDescription;
        Except
        End;

        // Get footprint from implementations
        FootprintName := '';
        Try
            ImplIter := SchComp.SchIterator_Create;
            ImplIter.AddFilter_ObjectSet(MkSet(eImplementation));
            Impl := ImplIter.FirstSchObject;
            While Impl <> Nil Do
            Begin
                Try
                    If Impl.ModelType = 'PCBLIB' Then
                    Begin
                        FootprintName := Impl.ModelName;
                        // Note: LibraryPath is not available in ISch_Implementation API
                        // We'll use the footprint name to search libraries when loading
                    End;
                Except
                End;
                Impl := ImplIter.NextSchObject;
            End;
            SchComp.SchIterator_Destroy(ImplIter);
        Except
        End;

        WriteLn(F, Q + 'designator' + Q + ':' + Q + EscapeJSONString(CompDesignator) + Q + ',');
        WriteLn(F, Q + 'value' + Q + ':' + Q + EscapeJSONString(CompValue) + Q + ',');
        WriteLn(F, Q + 'lib_reference' + Q + ':' + Q + EscapeJSONString(CompLibRef) + Q + ',');
        WriteLn(F, Q + 'description' + Q + ':' + Q + EscapeJSONString(CompDesc) + Q + ',');
        WriteLn(F, Q + 'footprint' + Q + ':' + Q + EscapeJSONString(FootprintName) + Q + ',');
        WriteLn(F, Q + 'x' + Q + ':' + FloatToStr(CoordToMils(SchComp.Location.X)) + ',');
        WriteLn(F, Q + 'y' + Q + ':' + FloatToStr(CoordToMils(SchComp.Location.Y)) + ',');

        // Export component pins
        WriteLn(F, Q + 'pins' + Q + ':[');
        PinCount := 0;
        Try
            PinIter := SchComp.SchIterator_Create;
            PinIter.AddFilter_ObjectSet(MkSet(ePin));
            SchPin := PinIter.FirstSchObject;
            While SchPin <> Nil Do
            Begin
                If PinCount > 0 Then WriteLn(F, ',');

                PinName := '';
                PinDesig := '';
                Try PinName := SchPin.Name; Except End;
                Try PinDesig := SchPin.Designator; Except End;

                WriteLn(F, Chr(123));
                WriteLn(F, Q + 'name' + Q + ':' + Q + EscapeJSONString(PinName) + Q + ',');
                WriteLn(F, Q + 'designator' + Q + ':' + Q + EscapeJSONString(PinDesig) + Q + ',');
                WriteLn(F, Q + 'x' + Q + ':' + FloatToStr(CoordToMils(SchPin.Location.X)) + ',');
                WriteLn(F, Q + 'y' + Q + ':' + FloatToStr(CoordToMils(SchPin.Location.Y)));
                Write(F, Chr(125));
                Inc(PinCount);

                SchPin := PinIter.NextSchObject;
            End;
            SchComp.SchIterator_Destroy(PinIter);
        Except
        End;

        WriteLn(F, '],');
        WriteLn(F, Q + 'pin_count' + Q + ':' + IntToStr(PinCount));

        Write(F, Chr(125));
        Inc(CompCount);
        SchComp := Iterator.NextSchObject;
    End;
    Doc.SchIterator_Destroy(Iterator);
    WriteLn(F, '],');

    // ================================================================
    // WIRES
    // ================================================================
    WriteLn(F, Q + 'wires' + Q + ':[');
    WireCount := 0;
    Iterator := Doc.SchIterator_Create;
    Iterator.AddFilter_ObjectSet(MkSet(eWire));

    SchWire := Iterator.FirstSchObject;
    While SchWire <> Nil Do
    Begin
        If WireCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'x1' + Q + ':' + FloatToStr(CoordToMils(SchWire.Location.X)) + ',');
        WriteLn(F, Q + 'y1' + Q + ':' + FloatToStr(CoordToMils(SchWire.Location.Y)) + ',');
        Try
            // ISch_Wire uses vertices, not Corner property
            VCount := SchWire.GetState_VerticesCount;
            If VCount >= 2 Then
            Begin
                WriteLn(F, Q + 'x2' + Q + ':' + FloatToStr(CoordToMils(SchWire.GetState_Vertex(VCount).X)) + ',');
                WriteLn(F, Q + 'y2' + Q + ':' + FloatToStr(CoordToMils(SchWire.GetState_Vertex(VCount).Y)));
            End
            Else
            Begin
                WriteLn(F, Q + 'x2' + Q + ':' + FloatToStr(CoordToMils(SchWire.Location.X)) + ',');
                WriteLn(F, Q + 'y2' + Q + ':' + FloatToStr(CoordToMils(SchWire.Location.Y)));
            End;
        Except
            WriteLn(F, Q + 'x2' + Q + ':0,');
            WriteLn(F, Q + 'y2' + Q + ':0');
        End;
        Write(F, Chr(125));
        Inc(WireCount);
        SchWire := Iterator.NextSchObject;
    End;
    Doc.SchIterator_Destroy(Iterator);
    WriteLn(F, '],');

    // ================================================================
    // NET LABELS
    // ================================================================
    WriteLn(F, Q + 'net_labels' + Q + ':[');
    NetCount := 0;
    Iterator := Doc.SchIterator_Create;
    Iterator.AddFilter_ObjectSet(MkSet(eNetLabel));

    SchNetLabel := Iterator.FirstSchObject;
    While SchNetLabel <> Nil Do
    Begin
        If NetCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + EscapeJSONString(SchNetLabel.Text) + Q + ',');
        WriteLn(F, Q + 'x' + Q + ':' + FloatToStr(CoordToMils(SchNetLabel.Location.X)) + ',');
        WriteLn(F, Q + 'y' + Q + ':' + FloatToStr(CoordToMils(SchNetLabel.Location.Y)));
        Write(F, Chr(125));
        Inc(NetCount);
        SchNetLabel := Iterator.NextSchObject;
    End;
    Doc.SchIterator_Destroy(Iterator);
    WriteLn(F, '],');

    // ================================================================
    // POWER PORTS
    // ================================================================
    WriteLn(F, Q + 'power_ports' + Q + ':[');
    PowerCount := 0;
    Iterator := Doc.SchIterator_Create;
    Iterator.AddFilter_ObjectSet(MkSet(ePowerObject));

    SchPowerObj := Iterator.FirstSchObject;
    While SchPowerObj <> Nil Do
    Begin
        If PowerCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + EscapeJSONString(SchPowerObj.Text) + Q + ',');
        WriteLn(F, Q + 'x' + Q + ':' + FloatToStr(CoordToMils(SchPowerObj.Location.X)) + ',');
        WriteLn(F, Q + 'y' + Q + ':' + FloatToStr(CoordToMils(SchPowerObj.Location.Y)));
        Write(F, Chr(125));
        Inc(PowerCount);
        SchPowerObj := Iterator.NextSchObject;
    End;
    Doc.SchIterator_Destroy(Iterator);
    WriteLn(F, '],');

    // ================================================================
    // JUNCTIONS (wire connection points)
    // ================================================================
    WriteLn(F, Q + 'junctions' + Q + ':[');
    JunctionCount := 0;
    Iterator := Doc.SchIterator_Create;
    Iterator.AddFilter_ObjectSet(MkSet(eJunction));

    SchJunction := Iterator.FirstSchObject;
    While SchJunction <> Nil Do
    Begin
        If JunctionCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'x' + Q + ':' + FloatToStr(CoordToMils(SchJunction.Location.X)) + ',');
        WriteLn(F, Q + 'y' + Q + ':' + FloatToStr(CoordToMils(SchJunction.Location.Y)));
        Write(F, Chr(125));
        Inc(JunctionCount);
        SchJunction := Iterator.NextSchObject;
    End;
    Doc.SchIterator_Destroy(Iterator);
    WriteLn(F, '],');

    // ================================================================
    // COMPILED NETLIST (from project compilation)
    // ================================================================
    WriteLn(F, Q + 'nets' + Q + ':[');
    Project := GetWorkspace.DM_FocusedProject;
    NetCount := 0;
    If Project <> Nil Then
    Begin
        Try
            Project.DM_Compile;

            // Iterate through flattened document nets
            FlatDoc := Project.DM_DocumentFlattened;
            If FlatDoc <> Nil Then
            Begin
                For I := 0 To FlatDoc.DM_NetCount - 1 Do
                Begin
                    NetObj := FlatDoc.DM_Nets(I);
                    If NetObj <> Nil Then
                    Begin
                        If NetCount > 0 Then WriteLn(F, ',');
                        WriteLn(F, Chr(123));
                        WriteLn(F, Q + 'name' + Q + ':' + Q + EscapeJSONString(NetObj.DM_NetName) + Q + ',');

                        // Export pins connected to this net
                        WriteLn(F, Q + 'pins' + Q + ':[');
                        For J := 0 To NetObj.DM_PinCount - 1 Do
                        Begin
                            NetPinObj := NetObj.DM_Pins(J);
                            If NetPinObj <> Nil Then
                            Begin
                                If J > 0 Then WriteLn(F, ',');

                                // Safely extract pin info using DM API
                                PinCompDesig := '';
                                PinPinDesig := '';
                                Try PinCompDesig := NetPinObj.DM_OwnerPartId; Except End;
                                Try PinPinDesig := NetPinObj.DM_PinNumber; Except End;

                                WriteLn(F, Chr(123));
                                WriteLn(F, Q + 'component' + Q + ':' + Q + EscapeJSONString(PinCompDesig) + Q + ',');
                                WriteLn(F, Q + 'pin' + Q + ':' + Q + EscapeJSONString(PinPinDesig) + Q);
                                Write(F, Chr(125));
                            End;
                        End;
                        WriteLn(F, ']');

                        Write(F, Chr(125));
                        Inc(NetCount);
                    End;
                End;
            End;
        Except
        End;
    End;
    WriteLn(F, '],');

    // ================================================================
    // STATISTICS
    // ================================================================
    WriteLn(F, Q + 'statistics' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'component_count' + Q + ':' + IntToStr(CompCount) + ',');
    WriteLn(F, Q + 'net_count' + Q + ':' + IntToStr(NetCount) + ',');
    WriteLn(F, Q + 'wire_count' + Q + ':' + IntToStr(WireCount) + ',');
    WriteLn(F, Q + 'power_port_count' + Q + ':' + IntToStr(PowerCount) + ',');
    WriteLn(F, Q + 'junction_count' + Q + ':' + IntToStr(JunctionCount));
    WriteLn(F, Chr(125));

    // Close JSON
    WriteLn(F, Chr(125));
    CloseFile(F);

    // Move temp file to final location
    Try
        If FileExists(FinalPath) Then DeleteFile(FinalPath);
        RenameFile(TempFilePath, FinalPath);
    Except
        // If rename fails, try copy
        Try
            CopyFile(TempFilePath, FinalPath);
            DeleteFile(TempFilePath);
        Except
        End;
    End;

    If Not SilentMode Then
    Begin
        ShowMessage('Schematic info exported!' + #13#10 +
                    'Components: ' + IntToStr(CompCount) + #13#10 +
                    'Nets: ' + IntToStr(NetCount) + #13#10 +
                    'Wires: ' + IntToStr(WireCount) + #13#10 +
                    'Power ports: ' + IntToStr(PowerCount) + #13#10 +
                    'File: ' + FinalPath);
    End;

    // Only write result if not in silent mode (when called internally from CreatePCBFromSchematic)
    If Not SilentMode Then
    Begin
        WriteRes(True, 'Schematic info exported: ' + IntToStr(CompCount) + ' components, ' +
                 IntToStr(NetCount) + ' nets, ' + IntToStr(WireCount) + ' wires');
    End;
End;


{..............................................................................}
{ AUTOMATE ECO DIALOG - Call Python script to automate ECO dialog            }
{..............................................................................}
Function AutomateECODialog : Boolean;
Var
    PythonScript, PythonExe, CommandLine : String;
    I : Integer;
Begin
    Result := False;
    
    // Wait for ECO dialog to appear
    For I := 1 To 10 Do
    Begin
        Sleep(500);
        Application.ProcessMessages;
    End;
    
    // Find Python script path
    If BasePath = '' Then
        BasePath := GetBasePath;
    
    PythonScript := BasePath + 'tools\automate_eco_dialog.py';
    
    // Try to find Python executable
    PythonExe := 'python';
    If FileExists('C:\Python39\python.exe') Then
        PythonExe := 'C:\Python39\python.exe'
    Else If FileExists('C:\Python310\python.exe') Then
        PythonExe := 'C:\Python310\python.exe'
    Else If FileExists('C:\Python311\python.exe') Then
        PythonExe := 'C:\Python311\python.exe'
    Else If FileExists('C:\Program Files\Python39\python.exe') Then
        PythonExe := 'C:\Program Files\Python39\python.exe';
    
    // Build command line
    CommandLine := PythonExe + ' "' + PythonScript + '"';
    
    // Execute Python script to automate the dialog
    // Note: DelphiScript doesn't have direct ShellExecute, so we'll use
    // a workaround - the Python script will be called from the Python side
    // For now, we'll rely on parameter-based automation
    // The Python script can be called separately if needed
    Try
        // Wait for dialog to be ready
        Sleep(2000);
        Application.ProcessMessages;
        
        // Return True to indicate we'll try parameter-based automation
        Result := True;
    Except
        Result := False;
    End;
End;

{..............................................................................}
{ CREATE A SINGLE SMD PAD AND ADD TO COMPONENT                                 }
{..............................................................................}
Procedure CreateSMDPad(Comp : IPCB_Component; PadName : String; PadX, PadY, PadW, PadH : Integer);
Var
    Pad : IPCB_Pad;
    Board : IPCB_Board;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then Exit;
    
    Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);
    If Pad = Nil Then Exit;
    
    Pad.X := PadX;
    Pad.Y := PadY;
    Pad.TopXSize := PadW;
    Pad.TopYSize := PadH;
    Pad.MidXSize := PadW;
    Pad.MidYSize := PadH;
    Pad.BotXSize := PadW;
    Pad.BotYSize := PadH;
    Pad.HoleSize := 0;
    Pad.Layer := eTopLayer;
    Pad.TopShape := eRectangular;
    Pad.Name := PadName;
    
    // Add pad to component (this automatically registers it with the board)
    Comp.AddPCBObject(Pad);
    
    // Also add to board explicitly to ensure it's registered
    Board.AddPCBObject(Pad);
    
    // Register with board system
    PCBServer.SendMessageToRobots(Pad.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, Pad.I_ObjectAddress);
    
    // Invalidate pad to ensure it's visible
    Pad.GraphicallyInvalidate;
End;

{..............................................................................}
{ CREATE A THROUGH-HOLE PAD AND ADD TO COMPONENT                               }
{..............................................................................}
Procedure CreateTHPad(Comp : IPCB_Component; PadName : String; PadX, PadY, PadSize, HoleSize : Integer);
Var
    Pad : IPCB_Pad;
    Board : IPCB_Board;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then Exit;
    
    Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);
    If Pad = Nil Then Exit;
    
    Pad.X := PadX;
    Pad.Y := PadY;
    Pad.TopXSize := PadSize;
    Pad.TopYSize := PadSize;
    Pad.MidXSize := PadSize;
    Pad.MidYSize := PadSize;
    Pad.BotXSize := PadSize;
    Pad.BotYSize := PadSize;
    Pad.HoleSize := HoleSize;
    Pad.Layer := eMultiLayer;
    Pad.TopShape := eRounded;
    Pad.Name := PadName;
    
    // Add pad to component (this automatically registers it with the board)
    Comp.AddPCBObject(Pad);
    
    // Also add to board explicitly to ensure it's registered
    Board.AddPCBObject(Pad);
    
    // Register with board system
    PCBServer.SendMessageToRobots(Pad.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, Pad.I_ObjectAddress);
    
    // Invalidate pad to ensure it's visible
    Pad.GraphicallyInvalidate;
End;

{..............................................................................}
{ ADD SILKSCREEN OUTLINE TO COMPONENT                                          }
{..............................................................................}
Procedure AddSilkOutline(Comp : IPCB_Component; CX, CY, HalfW, HalfH : Integer);
Var
    Track : IPCB_Track;
Begin
    // Top line
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track <> Nil Then
    Begin
        Track.X1 := CX - HalfW; Track.Y1 := CY + HalfH;
        Track.X2 := CX + HalfW; Track.Y2 := CY + HalfH;
        Track.Width := MilsToCoord(5);
        Track.Layer := eTopOverlay;
        Comp.AddPCBObject(Track);
    End;
    // Bottom line
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track <> Nil Then
    Begin
        Track.X1 := CX - HalfW; Track.Y1 := CY - HalfH;
        Track.X2 := CX + HalfW; Track.Y2 := CY - HalfH;
        Track.Width := MilsToCoord(5);
        Track.Layer := eTopOverlay;
        Comp.AddPCBObject(Track);
    End;
    // Left line
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track <> Nil Then
    Begin
        Track.X1 := CX - HalfW; Track.Y1 := CY - HalfH;
        Track.X2 := CX - HalfW; Track.Y2 := CY + HalfH;
        Track.Width := MilsToCoord(5);
        Track.Layer := eTopOverlay;
        Comp.AddPCBObject(Track);
    End;
    // Right line
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track <> Nil Then
    Begin
        Track.X1 := CX + HalfW; Track.Y1 := CY - HalfH;
        Track.X2 := CX + HalfW; Track.Y2 := CY + HalfH;
        Track.Width := MilsToCoord(5);
        Track.Layer := eTopOverlay;
        Comp.AddPCBObject(Track);
    End;
End;

{..............................................................................}
{ TRY TO LOAD FOOTPRINT FROM ALTIUM LIBRARY                                     }
{ Attempts to load a footprint from Altium's integrated or PCB libraries         }
{ Returns True if successful, False if footprint not found                       }
{ Note: This is a simplified implementation - full library search may require     }
{       access to library manager or integrated library APIs                     }
{..............................................................................}
Function TryLoadFootprintFromLibrary(Comp : IPCB_Component; FootprintName : String) : Boolean;
Var
    Board : IPCB_Board;
    PatternObj : IPCB_LibComponent;
Begin
    Result := False;
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then Exit;
    
    // In Altium, the Pattern property is typically read-only and set during ECO
    // However, we can try to use PCBServer to load from library
    // This is a placeholder - actual implementation would need library manager access
    Try
        // Attempt 1: Try to set pattern directly (likely will fail as it's read-only)
        Comp.Pattern := FootprintName;
        Result := True;
    Except
        // Pattern is read-only, so we need to load from library
        // This requires library manager or integrated library access
        // For now, return False to use manual pad creation
        Result := False;
    End;
End;

{..............................................................................}
{ NORMALIZE JSON STRING                                                         }
{ Removes newlines and extra whitespace from JSON for easier parsing            }
{..............................................................................}
Function NormalizeJSON(JSONStr : String) : String;
Var
    I : Integer;
    Ch : Char;
Begin
    Result := '';
    For I := 1 To Length(JSONStr) Do
    Begin
        Ch := JSONStr[I];
        If (Ch <> #10) And (Ch <> #13) And (Ch <> #9) Then
        Begin
            If (Ch = ' ') And (Length(Result) > 0) And (Result[Length(Result)] = ' ') Then
                Continue; // Skip consecutive spaces
            Result := Result + Ch;
        End;
    End;
End;

{..............................................................................}
{ READ FOOTPRINT FROM JSON FILE                                                 }
{ Reads footprint_libraries.json and extracts pad and silkscreen data          }
{ Returns True if footprint found, False otherwise                             }
{..............................................................................}
Function ReadFootprintFromJSON(FootprintName : String; Var PadsJSON, SilkscreenJSON : String) : Boolean;
Var
    JSONFile, Line, TmpStr, NormalizedLine : String;
    F : TextFile;
    InFootprintObject, InPadsArray, InSilkscreenObject : Boolean;
    BraceDepth, SquareBracketDepth : Integer;
    FootprintFound : Boolean;
    CurrentFootprintName : String;
    PadsStartPos, SilkscreenStartPos : Integer;
    I : Integer;
Begin
    Result := False;
    PadsJSON := '';
    SilkscreenJSON := '';
    
    If BasePath = '' Then BasePath := GetBasePath;
    JSONFile := BasePath + 'PCB_Project\footprint_libraries.json';
    
    If Not FileExists(JSONFile) Then Exit;
    
    Try
        AssignFile(F, JSONFile);
        Reset(F);
        
        InFootprintObject := False;
        InPadsArray := False;
        InSilkscreenObject := False;
        BraceDepth := 0;
        SquareBracketDepth := 0;
        FootprintFound := False;
        CurrentFootprintName := '';
        PadsStartPos := 0;
        SilkscreenStartPos := 0;
        
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            NormalizedLine := NormalizeJSON(Line);
            
            // Count braces and brackets
            For I := 1 To Length(NormalizedLine) Do
            Begin
                If NormalizedLine[I] = '{' Then Inc(BraceDepth)
                Else If NormalizedLine[I] = '}' Then Dec(BraceDepth)
                Else If NormalizedLine[I] = '[' Then Inc(SquareBracketDepth)
                Else If NormalizedLine[I] = ']' Then Dec(SquareBracketDepth);
            End;
            
            // Check for footprint_name
            If Pos('"footprint_name"', NormalizedLine) > 0 Then
            Begin
                TmpStr := Copy(NormalizedLine, Pos(':', NormalizedLine) + 1, Length(NormalizedLine));
                CurrentFootprintName := Trim(RemoveChars(TmpStr, '",'));
                If UpperCase(CurrentFootprintName) = UpperCase(FootprintName) Then
                Begin
                    FootprintFound := True;
                    InFootprintObject := True;
                End;
            End;
            
            // If we found the footprint, extract pads and silkscreen
            If FootprintFound And InFootprintObject Then
            Begin
                // Check for pads array start
                If (Pos('"pads"', NormalizedLine) > 0) And (Pos('[', NormalizedLine) > 0) Then
                Begin
                    InPadsArray := True;
                    PadsJSON := '[';
                    Continue;
                End;
                
                // Collect pads JSON
                If InPadsArray Then
                Begin
                    If SquareBracketDepth = 0 Then
                    Begin
                        InPadsArray := False;
                        PadsJSON := PadsJSON + ']';
                    End
                    Else
                    Begin
                        PadsJSON := PadsJSON + NormalizedLine;
                    End;
                End;
                
                // Check for silkscreen object start
                If (Pos('"silkscreen"', NormalizedLine) > 0) And (Pos('{', NormalizedLine) > 0) Then
                Begin
                    InSilkscreenObject := True;
                    SilkscreenJSON := '{';
                    Continue;
                End;
                
                // Collect silkscreen JSON
                If InSilkscreenObject Then
                Begin
                    If BraceDepth <= 1 Then
                    Begin
                        InSilkscreenObject := False;
                        SilkscreenJSON := SilkscreenJSON + '}';
                        // We have both pads and silkscreen, exit
                        Result := True;
                        Break;
                    End
                    Else
                    Begin
                        SilkscreenJSON := SilkscreenJSON + NormalizedLine;
                    End;
                End;
                
                // Check if we've left the footprint object
                If (BraceDepth = 0) And FootprintFound Then
                Begin
                    If (PadsJSON <> '') And (SilkscreenJSON <> '') Then
                        Result := True;
                    Break;
                End;
            End;
        End;
        
        CloseFile(F);
    Except
        Result := False;
    End;
End;

{..............................................................................}
{ PARSE PADS FROM JSON STRING                                                   }
{ Parses pad array JSON and creates pads on component                          }
{..............................................................................}
Procedure ParsePadsFromJSON(Comp : IPCB_Component; PadsJSON : String; CX, CY : Integer);
Var
    I, J : Integer;
    PadName, PadXStr, PadYStr, PadWStr, PadHStr, HoleSizeStr : String;
    PadX, PadY, PadW, PadH, HoleSize : Double;
    InPadObject : Boolean;
    BraceDepth : Integer;
    Line, TmpStr, Key, Value : String;
    F : TextFile;
    TempFile : String;
Begin
    If PadsJSON = '' Then Exit;
    
    // Write JSON to temp file for parsing
    TempFile := BasePath + 'PCB_Project\temp_pads.json';
    Try
        AssignFile(F, TempFile);
        Rewrite(F);
        Write(F, PadsJSON);
        CloseFile(F);
        
        AssignFile(F, TempFile);
        Reset(F);
        
        InPadObject := False;
        BraceDepth := 0;
        PadName := '';
        PadXStr := '';
        PadYStr := '';
        PadWStr := '';
        PadHStr := '';
        HoleSizeStr := '0';
        
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            Line := Trim(Line);
            
            For I := 1 To Length(Line) Do
            Begin
                If Line[I] = '{' Then
                Begin
                    Inc(BraceDepth);
                    If BraceDepth = 1 Then
                    Begin
                        InPadObject := True;
                        PadName := '';
                        PadXStr := '';
                        PadYStr := '';
                        PadWStr := '';
                        PadHStr := '';
                        HoleSizeStr := '0';
                    End;
                End
                Else If Line[I] = '}' Then
                Begin
                    Dec(BraceDepth);
                    If (BraceDepth = 0) And InPadObject Then
                    Begin
                        // Create pad
                        Try
                            PadX := StrToFloat(PadXStr);
                            PadY := StrToFloat(PadYStr);
                            PadW := StrToFloat(PadWStr);
                            PadH := StrToFloat(PadHStr);
                            HoleSize := StrToFloat(HoleSizeStr);
                            
                            If HoleSize > 0 Then
                                CreateTHPad(Comp, PadName, CX + MMsToCoord(PadX), CY + MMsToCoord(PadY), 
                                           MMsToCoord(PadW), MMsToCoord(HoleSize))
                            Else
                                CreateSMDPad(Comp, PadName, CX + MMsToCoord(PadX), CY + MMsToCoord(PadY), 
                                           MMsToCoord(PadW), MMsToCoord(PadH));
                        Except
                            // Skip invalid pad
                        End;
                        InPadObject := False;
                    End;
                End;
            End;
            
            // Parse key-value pairs
            If InPadObject Then
            Begin
                If Pos('"name"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    PadName := Trim(RemoveChars(TmpStr, '",'));
                End
                Else If Pos('"x"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    PadXStr := Trim(RemoveChars(TmpStr, '",'));
                End
                Else If Pos('"y"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    PadYStr := Trim(RemoveChars(TmpStr, '",'));
                End
                Else If Pos('"width"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    PadWStr := Trim(RemoveChars(TmpStr, '",'));
                End
                Else If Pos('"height"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    PadHStr := Trim(RemoveChars(TmpStr, '",'));
                End
                Else If Pos('"hole_size"', Line) > 0 Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    HoleSizeStr := Trim(RemoveChars(TmpStr, '",'));
                End;
            End;
        End;
        
        CloseFile(F);
        DeleteFile(TempFile);
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ PARSE SILKSCREEN FROM JSON STRING                                             }
{ Parses silkscreen object JSON and creates silkscreen outline                 }
{..............................................................................}
Procedure ParseSilkscreenFromJSON(Comp : IPCB_Component; SilkscreenJSON : String; CX, CY : Integer);
Var
    WidthStr, HeightStr : String;
    Width, Height : Double;
    I : Integer;
    Line, TmpStr : String;
    F : TextFile;
    TempFile : String;
Begin
    If SilkscreenJSON = '' Then Exit;
    
    // Write JSON to temp file for parsing
    TempFile := BasePath + 'PCB_Project\temp_silkscreen.json';
    Try
        AssignFile(F, TempFile);
        Rewrite(F);
        Write(F, SilkscreenJSON);
        CloseFile(F);
        
        AssignFile(F, TempFile);
        Reset(F);
        
        WidthStr := '';
        HeightStr := '';
        
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            Line := Trim(Line);
            
            If Pos('"width"', Line) > 0 Then
            Begin
                TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                WidthStr := Trim(RemoveChars(TmpStr, '",'));
            End
            Else If Pos('"height"', Line) > 0 Then
            Begin
                TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                HeightStr := Trim(RemoveChars(TmpStr, '",'));
            End;
        End;
        
        CloseFile(F);
        DeleteFile(TempFile);
        
        // Create silkscreen outline
        If (WidthStr <> '') And (HeightStr <> '') Then
        Begin
            Try
                Width := StrToFloat(WidthStr);
                Height := StrToFloat(HeightStr);
                AddSilkOutline(Comp, CX, CY, MMsToCoord(Width / 2), MMsToCoord(Height / 2));
            Except
                // Skip invalid silkscreen
            End;
        End;
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ ADD FOOTPRINT PADS TO A COMPONENT BASED ON FOOTPRINT NAME                    }
{ Creates proper pads with correct sizes from JSON file                        }
{ First tries to load from library, then tries JSON, falls back to generic     }
{..............................................................................}
Procedure AddFootprintPads(Comp : IPCB_Component; Footprint : String; PinCount : Integer);
Var
    FootprintLoaded : Boolean;
    CX, CY : Integer;
    PadsJSON, SilkscreenJSON : String;
    PadW, PadH, HalfPitch : Integer;
    I, PadsPerSide : Integer;
    PitchY, StartY, PadX, PadY : Integer;
Begin
    // First, try to load footprint from Altium's libraries
    FootprintLoaded := TryLoadFootprintFromLibrary(Comp, Footprint);
    
    If FootprintLoaded Then
    Begin
        // Footprint loaded successfully from library - no need to create pads manually
        Exit;
    End;
    
    // Try to read footprint data from JSON file
    If ReadFootprintFromJSON(Footprint, PadsJSON, SilkscreenJSON) Then
    Begin
        CX := Comp.X;
        CY := Comp.Y;
        
        // Normalize JSON strings
        PadsJSON := NormalizeJSON(PadsJSON);
        SilkscreenJSON := NormalizeJSON(SilkscreenJSON);
        
        // Parse and create pads from JSON
        ParsePadsFromJSON(Comp, PadsJSON, CX, CY);
        
        // Parse and create silkscreen from JSON
        ParseSilkscreenFromJSON(Comp, SilkscreenJSON, CX, CY);
    End;
    // No fallback - if JSON not found, component will have no pads (as per user requirement: NO hard-coding)
End;

{..............................................................................}
{ CREATE SILKSCREEN IN LIBRARY COMPONENT                                         }
{..............................................................................}
Procedure CreateLibSilkOutline(LibComp : IPCB_LibComponent; CX, CY, HalfW, HalfH : Integer);
Var
    Track : IPCB_Track;
Begin
    If LibComp = Nil Then Exit;
    
    Try
        // Top line
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        If Track <> Nil Then
        Begin
            Track.X1 := CX - HalfW; Track.Y1 := CY + HalfH;
            Track.X2 := CX + HalfW; Track.Y2 := CY + HalfH;
            Track.Width := MilsToCoord(5);
            Track.Layer := eTopOverlay;
            LibComp.AddPCBObject(Track);
        End;
        // Bottom line
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        If Track <> Nil Then
        Begin
            Track.X1 := CX - HalfW; Track.Y1 := CY - HalfH;
            Track.X2 := CX + HalfW; Track.Y2 := CY - HalfH;
            Track.Width := MilsToCoord(5);
            Track.Layer := eTopOverlay;
            LibComp.AddPCBObject(Track);
        End;
        // Left line
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        If Track <> Nil Then
        Begin
            Track.X1 := CX - HalfW; Track.Y1 := CY - HalfH;
            Track.X2 := CX - HalfW; Track.Y2 := CY + HalfH;
            Track.Width := MilsToCoord(5);
            Track.Layer := eTopOverlay;
            LibComp.AddPCBObject(Track);
        End;
        // Right line
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        If Track <> Nil Then
        Begin
            Track.X1 := CX + HalfW; Track.Y1 := CY - HalfH;
            Track.X2 := CX + HalfW; Track.Y2 := CY + HalfH;
            Track.Width := MilsToCoord(5);
            Track.Layer := eTopOverlay;
            LibComp.AddPCBObject(Track);
        End;
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ CREATE PAD IN LIBRARY COMPONENT                                               }
{ Creates a pad in a library component (for PCB library creation)               }
{..............................................................................}
Procedure CreateLibPad(LibComp : IPCB_LibComponent; PadName : String; PadX, PadY, PadW, PadH, HoleSize : Integer; IsSMD : Boolean);
Var
    Pad : IPCB_Pad;
Begin
    If LibComp = Nil Then Exit;
    
    Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);
    If Pad = Nil Then Exit;
    
    Try
        Pad.X := PadX;
        Pad.Y := PadY;
        Pad.TopXSize := PadW;
        Pad.TopYSize := PadH;
        Pad.MidXSize := PadW;
        Pad.MidYSize := PadH;
        Pad.BotXSize := PadW;
        Pad.BotYSize := PadH;
        Pad.HoleSize := HoleSize;
        
        If IsSMD Then
        Begin
            Pad.Layer := eTopLayer;
            Pad.TopShape := eRectangular;
        End
        Else
        Begin
            Pad.Layer := eMultiLayer;
            Pad.TopShape := eRounded;
        End;
        
        Pad.Name := PadName;
        LibComp.AddPCBObject(Pad);
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ PARSE LIBRARY PADS FROM JSON STRING                                           }
{ Parses pad array JSON and creates pads in library component                  }
{..............................................................................}
Procedure ParseLibPadsFromJSON(LibComp : IPCB_LibComponent; PadsJSON : String);
Var
    I, J, K, ColonPos : Integer;
    PadName, PadXStr, PadYStr, PadWStr, PadHStr, HoleSizeStr : String;
    PadX, PadY, PadW, PadH, HoleSize : Double;
    BraceDepth : Integer;
    Line, TmpStr : String;
    F : TextFile;
    TempFile : String;
Begin
    If (PadsJSON = '') Or (LibComp = Nil) Then Exit;
    
    // Ensure PadsJSON is not just whitespace or brackets
    TmpStr := Trim(PadsJSON);
    If (TmpStr = '') Or (TmpStr = '[') Or (TmpStr = '[]') Then Exit;
    
    // Write JSON to temp file for parsing
    TempFile := BasePath + 'PCB_Project\temp_lib_pads.json';
    Try
        AssignFile(F, TempFile);
        Rewrite(F);
        Write(F, PadsJSON);
        CloseFile(F);
        
        AssignFile(F, TempFile);
        Reset(F);
        
        BraceDepth := 0;
        PadName := '';
        PadXStr := '';
        PadYStr := '';
        PadWStr := '';
        PadHStr := '';
        HoleSizeStr := '0';
        
        // Read entire JSON content (may be on one or multiple lines)
        TmpStr := '';
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            If TmpStr <> '' Then TmpStr := TmpStr + ' ';
            TmpStr := TmpStr + Trim(Line);
        End;
        CloseFile(F);
        
        // Parse the complete JSON string - find each pad object and extract its values
        // PadsJSON should be a JSON array like: [{...}, {...}]
        Line := TmpStr;
        
        // Skip opening bracket and whitespace if present
        I := 1;
        While (I <= Length(Line)) And ((Line[I] = ' ') Or (Line[I] = '[') Or (Line[I] = #9)) Do Inc(I);
        
        // Find each pad object by looking for { ... } patterns
        While I <= Length(Line) Do
        Begin
            // Find start of pad object
            If Line[I] = '{' Then
            Begin
                // Reset pad values
                PadName := '';
                PadXStr := '';
                PadYStr := '';
                PadWStr := '';
                PadHStr := '';
                HoleSizeStr := '0';
                
                // Find the matching closing brace
                J := I + 1;
                BraceDepth := 1;
                While (J <= Length(Line)) And (BraceDepth > 0) Do
                Begin
                    If Line[J] = '{' Then Inc(BraceDepth)
                    Else If Line[J] = '}' Then Dec(BraceDepth);
                    Inc(J);
                End;
                
                // Extract the pad object JSON
                If BraceDepth = 0 Then
                Begin
                    TmpStr := Copy(Line, I, J - I);
                    
                    // Extract "name" value
                    ColonPos := Pos('"name"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 6; // Skip "name"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            If (K <= Length(TmpStr)) And (TmpStr[K] = '"') Then
                            Begin
                                Inc(K);
                                PadName := '';
                                While (K <= Length(TmpStr)) And (TmpStr[K] <> '"') Do
                                Begin
                                    PadName := PadName + TmpStr[K];
                                    Inc(K);
                                End;
                            End;
                        End;
                    End;
                    
                    // Extract "x" value
                    ColonPos := Pos('"x"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 3; // Skip "x"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            PadXStr := '';
                            While (K <= Length(TmpStr)) And (TmpStr[K] <> ',') And (TmpStr[K] <> '}') And (TmpStr[K] <> ']') Do
                            Begin
                                PadXStr := PadXStr + TmpStr[K];
                                Inc(K);
                            End;
                            PadXStr := Trim(PadXStr);
                        End;
                    End;
                    
                    // Extract "y" value
                    ColonPos := Pos('"y"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 3; // Skip "y"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            PadYStr := '';
                            While (K <= Length(TmpStr)) And (TmpStr[K] <> ',') And (TmpStr[K] <> '}') And (TmpStr[K] <> ']') Do
                            Begin
                                PadYStr := PadYStr + TmpStr[K];
                                Inc(K);
                            End;
                            PadYStr := Trim(PadYStr);
                        End;
                    End;
                    
                    // Extract "width" value
                    ColonPos := Pos('"width"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 7; // Skip "width"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            PadWStr := '';
                            While (K <= Length(TmpStr)) And (TmpStr[K] <> ',') And (TmpStr[K] <> '}') And (TmpStr[K] <> ']') Do
                            Begin
                                PadWStr := PadWStr + TmpStr[K];
                                Inc(K);
                            End;
                            PadWStr := Trim(PadWStr);
                        End;
                    End;
                    
                    // Extract "height" value
                    ColonPos := Pos('"height"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 8; // Skip "height"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            PadHStr := '';
                            While (K <= Length(TmpStr)) And (TmpStr[K] <> ',') And (TmpStr[K] <> '}') And (TmpStr[K] <> ']') Do
                            Begin
                                PadHStr := PadHStr + TmpStr[K];
                                Inc(K);
                            End;
                            PadHStr := Trim(PadHStr);
                        End;
                    End;
                    
                    // Extract "hole_size" value
                    ColonPos := Pos('"hole_size"', TmpStr);
                    If ColonPos > 0 Then
                    Begin
                        K := ColonPos + 11; // Skip "hole_size"
                        ColonPos := Pos(':', Copy(TmpStr, K, Length(TmpStr)));
                        If ColonPos > 0 Then
                        Begin
                            K := K + ColonPos; // Position after ':'
                            While (K <= Length(TmpStr)) And (TmpStr[K] = ' ') Do Inc(K);
                            HoleSizeStr := '';
                            While (K <= Length(TmpStr)) And (TmpStr[K] <> ',') And (TmpStr[K] <> '}') And (TmpStr[K] <> ']') Do
                            Begin
                                HoleSizeStr := HoleSizeStr + TmpStr[K];
                                Inc(K);
                            End;
                            HoleSizeStr := Trim(HoleSizeStr);
                            If HoleSizeStr = '' Then HoleSizeStr := '0';
                        End;
                    End;
                    
                    // Create pad if all required fields are present
                    If (PadName <> '') And (PadXStr <> '') And (PadYStr <> '') And 
                       (PadWStr <> '') And (PadHStr <> '') Then
                    Begin
                        Try
                            PadX := StrToFloat(PadXStr);
                            PadY := StrToFloat(PadYStr);
                            PadW := StrToFloat(PadWStr);
                            PadH := StrToFloat(PadHStr);
                            If HoleSizeStr = '' Then HoleSizeStr := '0';
                            HoleSize := StrToFloat(HoleSizeStr);
                            
                            CreateLibPad(LibComp, PadName, MMsToCoord(PadX), MMsToCoord(PadY), 
                                       MMsToCoord(PadW), MMsToCoord(PadH), MMsToCoord(HoleSize), 
                                       HoleSize = 0);
                        Except
                            // Skip invalid pad - conversion failed
                        End;
                    End;
                    
                    // Move to after this pad object
                    I := J;
                End
                Else
                    Inc(I);
            End
            Else
                Inc(I);
        End;
        
        // File already closed after reading at line 1407, so just delete temp file
        DeleteFile(TempFile);
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ PARSE LIBRARY SILKSCREEN FROM JSON STRING                                     }
{ Parses silkscreen object JSON and creates silkscreen outline in library      }
{..............................................................................}
Procedure ParseLibSilkscreenFromJSON(LibComp : IPCB_LibComponent; SilkscreenJSON : String);
Var
    WidthStr, HeightStr : String;
    Width, Height : Double;
    I, ColonPos : Integer;
    Line, TmpStr : String;
    F : TextFile;
    TempFile : String;
Begin
    If (SilkscreenJSON = '') Or (LibComp = Nil) Then Exit;
    
    // Write JSON to temp file for parsing
    TempFile := BasePath + 'PCB_Project\temp_lib_silkscreen.json';
    Try
        AssignFile(F, TempFile);
        Rewrite(F);
        Write(F, SilkscreenJSON);
        CloseFile(F);
        
        AssignFile(F, TempFile);
        Reset(F);
        
        // Read entire JSON content (may be on one or multiple lines)
        TmpStr := '';
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            If TmpStr <> '' Then TmpStr := TmpStr + ' ';
            TmpStr := TmpStr + Trim(Line);
        End;
        CloseFile(F);
        DeleteFile(TempFile);
        
        // Ensure JSON is not just whitespace or braces
        TmpStr := Trim(TmpStr);
        If (TmpStr = '') Or (TmpStr = '{') Or (TmpStr = '{}') Then Exit;
        
        WidthStr := '';
        HeightStr := '';
        
        // Parse the complete JSON string to extract width and height
        // Extract "width" value
        I := Pos('"width"', TmpStr);
        If I > 0 Then
        Begin
            I := I + 7; // Skip "width"
            ColonPos := Pos(':', Copy(TmpStr, I, Length(TmpStr)));
            If ColonPos > 0 Then
            Begin
                I := I + ColonPos; // Position after ':'
                While (I <= Length(TmpStr)) And (TmpStr[I] = ' ') Do Inc(I);
                WidthStr := '';
                While (I <= Length(TmpStr)) And (TmpStr[I] <> ',') And (TmpStr[I] <> '}') And (TmpStr[I] <> ']') Do
                Begin
                    WidthStr := WidthStr + TmpStr[I];
                    Inc(I);
                End;
                WidthStr := Trim(WidthStr);
            End;
        End;
        
        // Extract "height" value
        I := Pos('"height"', TmpStr);
        If I > 0 Then
        Begin
            I := I + 8; // Skip "height"
            ColonPos := Pos(':', Copy(TmpStr, I, Length(TmpStr)));
            If ColonPos > 0 Then
            Begin
                I := I + ColonPos; // Position after ':'
                While (I <= Length(TmpStr)) And (TmpStr[I] = ' ') Do Inc(I);
                HeightStr := '';
                While (I <= Length(TmpStr)) And (TmpStr[I] <> ',') And (TmpStr[I] <> '}') And (TmpStr[I] <> ']') Do
                Begin
                    HeightStr := HeightStr + TmpStr[I];
                    Inc(I);
                End;
                HeightStr := Trim(HeightStr);
            End;
        End;
        
        // Create silkscreen outline (tracks) if width and height are found
        If (WidthStr <> '') And (HeightStr <> '') Then
        Begin
            Try
                Width := StrToFloat(WidthStr);
                Height := StrToFloat(HeightStr);
                CreateLibSilkOutline(LibComp, 0, 0, MMsToCoord(Width / 2), MMsToCoord(Height / 2));
            Except
                // Skip invalid silkscreen
            End;
        End;
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ CREATE FOOTPRINT IN LIBRARY FROM JSON                                         }
{ Creates a library component using JSON data from footprint_libraries.json    }
{..............................................................................}
Procedure CreateFootprintInLibraryFromJSON(LibDoc : IPCB_Library; FootprintName : String; PadsJSON, SilkscreenJSON : String);
Var
    LibComp : IPCB_LibComponent;
Begin
    If (LibDoc = Nil) Or (PadsJSON = '') Then Exit;
    
    // Create new library component
    LibComp := Nil;
    Try
        LibComp := PCBServer.CreatePCBLibComp;
        If LibComp = Nil Then Exit;
        
        LibComp.Name := FootprintName;
        LibDoc.RegisterComponent(LibComp);
        
        If Length(LibComp.Name) = 0 Then
        Begin
            Exit;
        End;
        
        Application.ProcessMessages;
    Except
        Exit;
    End;
    
    If LibComp = Nil Then Exit;
    
    Try
        // Normalize JSON strings
        PadsJSON := NormalizeJSON(PadsJSON);
        SilkscreenJSON := NormalizeJSON(SilkscreenJSON);
        
        // Parse and create pads from JSON
        ParseLibPadsFromJSON(LibComp, PadsJSON);
        
        // Parse and create silkscreen from JSON
        ParseLibSilkscreenFromJSON(LibComp, SilkscreenJSON);
        
        // Refresh library view
        PCBServer.PostProcess;
        Application.ProcessMessages;
    Except
        // Silently handle errors
    End;
End;

{..............................................................................}
{ CREATE FOOTPRINT IN LIBRARY FROM SPECIFICATION                                 }
{ Creates a library component with pads based on footprint name and specs      }
{..............................................................................}
Procedure CreateFootprintInLibrary(LibDoc : IPCB_Library; FootprintName : String; PinCount : Integer);
Var
    PadsJSON, SilkscreenJSON : String;
Begin
    If LibDoc = Nil Then Exit;
    
    // Try to read footprint data from JSON file
    If ReadFootprintFromJSON(FootprintName, PadsJSON, SilkscreenJSON) Then
    Begin
        // Use JSON-based creation
        CreateFootprintInLibraryFromJSON(LibDoc, FootprintName, PadsJSON, SilkscreenJSON);
    End;
    // No fallback - if JSON not found, footprint will not be created (as per user requirement: NO hard-coding)
End;

{..............................................................................}
{ CREATE PCB LIBRARY FROM GENERATED FOOTPRINT SPECIFICATIONS                    }
{ Reads footprint_libraries.json and creates Altium PCB library files           }
{..............................................................................}
Procedure CreatePCBLibraries;
Var
    LibFilePath, FootprintFile, Line, FootprintName, TmpStr : String;
    F : TextFile;
    LibDoc : IPCB_Library;
    ServerDoc : IServerDocument;
    FootprintCount, I, PinCount, GlobalBraceDepth, PrevBraceDepth, RetryCount : Integer;
    SquareBracketDepth, PrevSquareDepth, ColonPos : Integer;
    InFootprints, InFootprintObject, InPadsArray, InSilkscreenObject : Boolean;
    Section : String;
    PadsJSON, SilkscreenJSON : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    
    FootprintFile := GetFootprintLibrariesFile;
    If Not FileExists(FootprintFile) Then
    Begin
        WriteRes(False, 'Footprint libraries file not found: ' + FootprintFile);
        Exit;
    End;
    
    // Create a new PCB library file
    LibFilePath := BasePath + 'PCB_Project\GeneratedFootprints.PcbLib';
    
    // Create new PCB library document
    ResetParameters;
    AddStringParameter('ObjectKind', 'PcbLib');
    AddStringParameter('FileName', LibFilePath);
    RunProcess('WorkspaceManager:OpenObject');
    Sleep(3000);
    Application.ProcessMessages;
    Sleep(1000);
    Application.ProcessMessages;
    
    // Get the library document - try multiple times
    ServerDoc := Nil;
    RetryCount := 0;
    While (ServerDoc = Nil) And (RetryCount < 10) Do
    Begin
        ServerDoc := Client.GetDocumentByPath(LibFilePath);
        If ServerDoc = Nil Then
        Begin
            Sleep(500);
            Application.ProcessMessages;
            Inc(RetryCount);
        End;
    End;
    
    If ServerDoc = Nil Then
    Begin
        WriteRes(False, 'Failed to open PCB library document');
        Exit;
    End;
    
    // Get the PCB library interface
    // First, activate the library document
    Try
        Client.ShowDocument(ServerDoc);
        Sleep(2000);
        Application.ProcessMessages;
        
        // Get library from current PCB library document
        // Note: PCBServer.GetCurrentPCBLibrary requires the library to be the active document
        LibDoc := PCBServer.GetCurrentPCBLibrary;
        If LibDoc = Nil Then
        Begin
            // Try again with longer wait
            Application.ProcessMessages;
            Sleep(2000);
            Application.ProcessMessages;
            LibDoc := PCBServer.GetCurrentPCBLibrary;
        End;
        
        If LibDoc = Nil Then
        Begin
            WriteRes(False, 'Cannot access PCB library interface. Library document may not be properly opened. Please ensure the library document is open and active in Altium.');
            Exit;
        End;
    Except
        WriteRes(False, 'Error accessing library document: ' + LibFilePath);
        Exit;
    End;
    
    // Parse footprint_libraries.json and create footprints
    AssignFile(F, FootprintFile);
    Reset(F);
    
    FootprintCount := 0;
    InFootprints := False;
    InFootprintObject := False;
    GlobalBraceDepth := 0;
    FootprintName := '';
    PadsJSON := '';
    SilkscreenJSON := '';
    Section := '';
    SquareBracketDepth := 0;
    InPadsArray := False;
    InSilkscreenObject := False;
    
    While Not Eof(F) Do
    Begin
        ReadLn(F, Line);
        Line := Trim(Line);
        
        // Track brace and bracket depth
        PrevBraceDepth := GlobalBraceDepth;
        PrevSquareDepth := SquareBracketDepth;
        For I := 1 To Length(Line) Do
        Begin
            If Line[I] = '{' Then Inc(GlobalBraceDepth)
            Else If Line[I] = '}' Then Dec(GlobalBraceDepth)
            Else If Line[I] = '[' Then Inc(SquareBracketDepth)
            Else If Line[I] = ']' Then Dec(SquareBracketDepth);
        End;
        
        // Detect footprints array
        If Pos('"footprints"', Line) > 0 Then
        Begin
            InFootprints := True;
            Continue;
        End;
        
        // Detect footprint object start
        If InFootprints And (Pos('{', Line) > 0) And (PrevBraceDepth = 1) And (GlobalBraceDepth = 2) Then
        Begin
            InFootprintObject := True;
            FootprintName := '';
            PadsJSON := '';
            SilkscreenJSON := '';
            Section := '';
            InPadsArray := False;
            InSilkscreenObject := False;
            Continue;
        End;
        
        // Parse footprint fields
        If InFootprintObject Then
        Begin
            If Pos('"footprint_name"', Line) > 0 Then
            Begin
                TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                FootprintName := Trim(RemoveChars(TmpStr, '",'));
            End
            Else If Pos('"pads"', Line) > 0 Then
            Begin
                Section := 'pads';
                PadsJSON := '';
                InPadsArray := False;
                // Check if opening bracket is on same line
                ColonPos := Pos('[', Line);
                If ColonPos > 0 Then
                Begin
                    InPadsArray := True;
                    PadsJSON := Copy(Line, ColonPos, Length(Line));
                End;
            End
            Else If Pos('"silkscreen"', Line) > 0 Then
            Begin
                Section := 'silkscreen';
                SilkscreenJSON := '';
                InSilkscreenObject := False;
                // Check if opening brace is on same line
                ColonPos := Pos('{', Line);
                If ColonPos > 0 Then
                Begin
                    InSilkscreenObject := True;
                    SilkscreenJSON := Copy(Line, ColonPos, Length(Line));
                End;
            End
            Else If (Section = 'pads') Then
            Begin
                // Check if we're entering the pads array (bracket depth changed from 0 to >0)
                If (PrevSquareDepth = 0) And (SquareBracketDepth > 0) And Not InPadsArray Then
                Begin
                    InPadsArray := True;
                    ColonPos := Pos('[', Line);
                    If ColonPos > 0 Then
                        PadsJSON := Copy(Line, ColonPos, Length(Line))
                    Else
                        PadsJSON := '[' + Line;
                End
                // Collect pads array content while we're inside it
                Else If InPadsArray Then
                Begin
                    If PadsJSON <> '' Then PadsJSON := PadsJSON + ' ';
                    PadsJSON := PadsJSON + Line;
                    // Check if we're exiting the pads array (bracket depth changed from >0 to 0)
                    If (PrevSquareDepth > 0) And (SquareBracketDepth = 0) Then
                    Begin
                        InPadsArray := False;
                        Section := '';
                    End;
                End;
            End
            Else If (Section = 'silkscreen') Then
            Begin
                // Check if we're entering the silkscreen object (brace depth changed from 2 to 3)
                If (PrevBraceDepth = 2) And (GlobalBraceDepth = 3) And Not InSilkscreenObject Then
                Begin
                    InSilkscreenObject := True;
                    ColonPos := Pos('{', Line);
                    If ColonPos > 0 Then
                        SilkscreenJSON := Copy(Line, ColonPos, Length(Line))
                    Else
                        SilkscreenJSON := '{' + Line;
                End
                // Collect silkscreen object content while we're inside it
                Else If InSilkscreenObject Then
                Begin
                    If SilkscreenJSON <> '' Then SilkscreenJSON := SilkscreenJSON + ' ';
                    SilkscreenJSON := SilkscreenJSON + Line;
                    // Check if we're exiting the silkscreen object (brace depth changed from 3 to 2)
                    If (PrevBraceDepth = 3) And (GlobalBraceDepth = 2) Then
                    Begin
                        InSilkscreenObject := False;
                        Section := '';
                    End;
                End;
            End;
        End;
        
        // Detect footprint object end
        If InFootprintObject And (PrevBraceDepth = 2) And (GlobalBraceDepth = 1) And (Pos('}', Line) > 0) Then
        Begin
            // Create footprint in library
            If (FootprintName <> '') And (PadsJSON <> '') Then
            Begin
                Try
                    CreateFootprintInLibraryFromJSON(LibDoc, FootprintName, PadsJSON, SilkscreenJSON);
                    Inc(FootprintCount);
                    Application.ProcessMessages;
                    Sleep(50);
                Except
                    // Skip invalid footprints
                End;
            End;
            InFootprintObject := False;
            InPadsArray := False;
            InSilkscreenObject := False;
        End;
        
        // Exit footprints array
        If InFootprints And (Pos(']', Line) > 0) And (GlobalBraceDepth = 0) Then
        Begin
            InFootprints := False;
        End;
    End;
    
    CloseFile(F);
    
    // Save the library
    Try
        ServerDoc.DoFileSave(LibFilePath);
        Application.ProcessMessages;
        Sleep(1000);
    Except
        // Continue even if save fails
    End;
    
    WriteRes(True, 'Created ' + IntToStr(FootprintCount) + ' footprints in library');
End;

{..............................................................................}
{ BUILD PCB FROM SCHEMATIC DATA (Direct API - No ECO)                          }
{ Reads schematic JSON and creates PCB components directly using PCBServer API }
{..............................................................................}
Procedure BuildPCBFromSchematicData;
Var
    Board : IPCB_Board;
    Comp : IPCB_Component;
    Net : IPCB_Net;
    Pad : IPCB_Pad;
    SchInfoFile, Line, CompDesig, CompFootprint, CompValue, NetName, PinComp, PinNum, TmpStr : String;
    F, DebugF : TextFile;
    I, CompCount, NetCount, GlobalBraceDepth, PrevDepth : Integer;
    CompX, CompY : Double;
    CompPinCount : Integer;
    Section : String;
    InComponentObject : Boolean;
    CurrentNet : IPCB_Net;
    PadFound : Boolean;
    Iter : IPCB_BoardIterator;
    CompIter : IPCB_BoardIterator;
    PadIter : IPCB_BoardIterator;
    DebugLogPath : String;
    GridX, GridY, GridCol : Integer;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open. Create PCB first.');
        Exit;
    End;

    If BasePath = '' Then BasePath := GetBasePath;
    SchInfoFile := GetSchematicInfoFile;
    
    If Not FileExists(SchInfoFile) Then
    Begin
        WriteRes(False, 'Schematic info file not found: ' + SchInfoFile);
        Exit;
    End;

    // Debug log file
    DebugLogPath := BasePath + 'build_pcb_debug.log';
    AssignFile(DebugF, DebugLogPath);
    Rewrite(DebugF);
    WriteLn(DebugF, 'BuildPCBFromSchematicData started');
    WriteLn(DebugF, 'SchInfoFile: ' + SchInfoFile);

    PCBServer.PreProcess;
    CompCount := 0;
    NetCount := 0;
    GlobalBraceDepth := 0;
    Section := '';
    InComponentObject := False;
    CompDesig := '';
    CompFootprint := '';
    CompValue := '';
    CompX := 0;
    CompY := 0;
    CompPinCount := 2;
    GridCol := 0;

    Try
        AssignFile(F, SchInfoFile);
        Reset(F);
        
        While Not Eof(F) Do
        Begin
            ReadLn(F, Line);
            Line := Trim(Line);
            
            // Save previous depth before counting braces on this line
            PrevDepth := GlobalBraceDepth;
            
            // Count ALL braces on this line to track global depth
            For I := 1 To Length(Line) Do
            Begin
                If Line[I] = '{' Then
                    Inc(GlobalBraceDepth)
                Else If Line[I] = '}' Then
                    Dec(GlobalBraceDepth);
            End;
            
            // ---- DETECT SECTION BOUNDARIES ----
            // Section keys appear at depth 1 (inside top-level object)
            If Pos('"components"', Line) > 0 Then
            Begin
                Section := 'components';
                WriteLn(DebugF, 'Entered components section');
                Continue;
            End;
            
            If Pos('"wires"', Line) > 0 Then
            Begin
                Section := 'wires';
                InComponentObject := False;
                WriteLn(DebugF, 'Entered wires section, total components: ' + IntToStr(CompCount));
                Continue;
            End;
            
            If Pos('"power_ports"', Line) > 0 Then
            Begin
                Section := 'power_ports';
                Continue;
            End;
            
            If Pos('"junctions"', Line) > 0 Then
            Begin
                Section := 'junctions';
                Continue;
            End;
            
            If Pos('"nets"', Line) > 0 Then
            Begin
                Section := 'nets';
                WriteLn(DebugF, 'Entered nets section');
                Continue;
            End;
            
            // ================================================================
            // COMPONENTS SECTION
            // ================================================================
            If Section = 'components' Then
            Begin
                // Detect NEW component start: depth transitioned from 1 to 2
                // This happens when we see the opening { of a component object
                If (PrevDepth = 1) And (GlobalBraceDepth >= 2) Then
                Begin
                    InComponentObject := True;
                    CompDesig := '';
                    CompFootprint := '';
                    CompValue := '';
                    CompX := 0;
                    CompY := 0;
                    CompPinCount := 2;
                End;
                
                // Parse fields ONLY at depth 2 (component level)
                // Depth 3+ means we are inside nested objects like "pins" - SKIP
                If InComponentObject And (GlobalBraceDepth = 2) Then
                Begin
                    If Pos('"designator"', Line) > 0 Then
                    Begin
                        TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                        CompDesig := Trim(RemoveChars(TmpStr, '",'));
                    End;
                    
                    If Pos('"footprint"', Line) > 0 Then
                    Begin
                        TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                        CompFootprint := Trim(RemoveChars(TmpStr, '",'));
                    End;
                    
                    If Pos('"value"', Line) > 0 Then
                    Begin
                        TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                        CompValue := Trim(RemoveChars(TmpStr, '",'));
                    End;
                    
                    If Pos('"x"', Line) > 0 Then
                    Begin
                        Try
                            TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                            TmpStr := Trim(RemoveChars(TmpStr, '",'));
                            CompX := StrToFloat(TmpStr);
                        Except
                            CompX := 0;
                        End;
                    End;
                    
                    If Pos('"y"', Line) > 0 Then
                    Begin
                        Try
                            TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                            TmpStr := Trim(RemoveChars(TmpStr, '",'));
                            CompY := StrToFloat(TmpStr);
                        Except
                            CompY := 0;
                        End;
                    End;
                    
                    If Pos('"pin_count"', Line) > 0 Then
                    Begin
                        Try
                            TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                            TmpStr := Trim(RemoveChars(TmpStr, '",'));
                            CompPinCount := StrToInt(TmpStr);
                        Except
                            CompPinCount := 2;
                        End;
                    End;
                End;
                
                // Detect component END: depth transitioned from 2 to 1
                // This happens when we see the closing } of a component object
                If (PrevDepth >= 2) And (GlobalBraceDepth = 1) And InComponentObject Then
                Begin
                    If CompDesig <> '' Then
                    Begin
                        Try
                            Comp := PCBServer.PCBObjectFactory(eComponentObject, eNoDimension, eCreate_Default);
                            If Comp <> Nil Then
                            Begin
                                Comp.Name.Text := CompDesig;
                                
                                // Set Pattern name (even if not from library, this helps Altium recognize the component)
                                Try
                                    Comp.Pattern := CompFootprint;
                                Except
                                    // Pattern might be read-only, continue anyway
                                End;
                                
                                // Place components in a grid layout on the PCB
                                // 800 mils apart, 8 per row (wider spacing for footprint pads)
                                GridX := (CompCount Mod 8) * 800;
                                GridY := (CompCount Div 8) * 800;
                                Comp.X := MilsToCoord(1000 + GridX);
                                Comp.Y := MilsToCoord(1000 + GridY);
                                
                                Board.AddPCBObject(Comp);
                                PCBServer.SendMessageToRobots(Comp.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, Comp.I_ObjectAddress);
                                
                                // Add footprint pads based on the component's package type
                                AddFootprintPads(Comp, CompFootprint, CompPinCount);
                                
                                // Refresh component to ensure pads are visible
                                Comp.GraphicallyInvalidate;
                                PCBServer.SendMessageToRobots(Comp.I_ObjectAddress, c_Broadcast, PCBM_EndModify, Comp.I_ObjectAddress);
                                
                                Inc(CompCount);
                                
                                WriteLn(DebugF, 'Created component #' + IntToStr(CompCount) + ': ' + CompDesig + ' [' + CompFootprint + '] pins=' + IntToStr(CompPinCount));
                            End
                            Else
                                WriteLn(DebugF, 'ERROR: PCBObjectFactory returned Nil for ' + CompDesig);
                        Except
                            WriteLn(DebugF, 'EXCEPTION creating component: ' + CompDesig);
                        End;
                    End
                    Else
                        WriteLn(DebugF, 'WARNING: Empty designator at component end');
                    
                    InComponentObject := False;
                End;
            End;
            
            // ================================================================
            // NETS SECTION
            // ================================================================
            If Section = 'nets' Then
            Begin
                // Net name at depth 2 (inside net object, not inside pins)
                If (GlobalBraceDepth = 2) And (Pos('"name"', Line) > 0) Then
                Begin
                    TmpStr := Copy(Line, Pos(':', Line) + 1, Length(Line));
                    NetName := Trim(RemoveChars(TmpStr, '",'));
                    
                    If NetName <> '' Then
                    Begin
                        Try
                            // Check if net already exists
                            CurrentNet := Nil;
                            Iter := Board.BoardIterator_Create;
                            Iter.AddFilter_ObjectSet(MkSet(eNetObject));
                            Iter.AddFilter_LayerSet(AllLayers);
                            Net := Iter.FirstPCBObject;
                            While Net <> Nil Do
                            Begin
                                If UpperCase(Net.Name) = UpperCase(NetName) Then
                                Begin
                                    CurrentNet := Net;
                                    Break;
                                End;
                                Net := Iter.NextPCBObject;
                            End;
                            Board.BoardIterator_Destroy(Iter);
                            
                            // Create net if it doesn't exist
                            If CurrentNet = Nil Then
                            Begin
                                CurrentNet := PCBServer.PCBObjectFactory(eNetObject, eNoDimension, eCreate_Default);
                                If CurrentNet <> Nil Then
                                Begin
                                    CurrentNet.Name := NetName;
                                    Board.AddPCBObject(CurrentNet);
                                    Inc(NetCount);
                                End;
                            End;
                        Except
                            CurrentNet := Nil;
                        End;
                    End;
                End;
            End;
        End;
        
        CloseFile(F);
    Except
        WriteLn(DebugF, 'EXCEPTION reading schematic info file');
        CloseFile(DebugF);
        WriteRes(False, 'Error reading schematic info file');
        Exit;
    End;
    
    PCBServer.PostProcess;
    Board.GraphicallyInvalidate;
    
    WriteLn(DebugF, 'Build complete: ' + IntToStr(CompCount) + ' components, ' + IntToStr(NetCount) + ' nets');
    CloseFile(DebugF);
    
    WriteRes(True, 'PCB_BUILT|' + IntToStr(CompCount) + '|' + IntToStr(NetCount) + '|' + Board.FileName);
End;

{..............................................................................}
{ CREATE PCB FROM SCHEMATIC                                                    }
{ Creates blank PCB, adds to project, then builds from schematic data directly }
{..............................................................................}
Procedure CreatePCBFromSchematic;
Var
    Project : IProject;
    Doc : ISch_Document;
    PCBDocPath, ProjectPath, SchDocPath, BaseName, SchInfoFile, Line : String;
    ServerDoc : IServerDocument;
    Counter : Integer;
    Board : IPCB_Board;
    CompCount : Integer;
    BoardFileName, NewPCBFileName : String;
    I : Integer;
    ProjDoc : IDocument;
    FoundSch : Boolean;
    TempServerDoc : IServerDocument;
    Iter : IPCB_BoardIterator;
    Comp : IPCB_Component;
    F : TextFile;
Begin
    Project := GetWorkspace.DM_FocusedProject;
    If Project = Nil Then
    Begin
        WriteRes(False, 'No project found');
        Exit;
    End;

    // Try to get the current schematic document
    Doc := SchServer.GetCurrentSchDocument;
    
    // If no schematic is open, try to find and open one from the project
    If Doc = Nil Then
    Begin
        // Look for schematic documents in the project
        FoundSch := False;
        
        For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
        Begin
            ProjDoc := Project.DM_LogicalDocuments(I);
            If ProjDoc <> Nil Then
            Begin
                If (UpperCase(ExtractFileExt(ProjDoc.DM_FullPath)) = '.SCHDOC') Or
                   (UpperCase(ExtractFileExt(ProjDoc.DM_FullPath)) = '.SCH') Then
                Begin
                    // Found a schematic - try to open it
                    Try
                        TempServerDoc := Client.OpenDocument('SCH', ProjDoc.DM_FullPath);
                        If TempServerDoc <> Nil Then
                        Begin
                            Client.ShowDocument(TempServerDoc);
                            Sleep(2000);
                            Application.ProcessMessages;
                            
                            // Re-check if schematic is now open
                            Doc := SchServer.GetCurrentSchDocument;
                            If Doc <> Nil Then
                            Begin
                                FoundSch := True;
                                Break;
                            End;
                        End;
                    Except
                    End;
                End;
            End;
        End;
        
        // If still no schematic, try to open by path from schematic_info.json
        If Doc = Nil Then
        Begin
            // Try to get schematic path from the exported JSON file
            SchInfoFile := GetSchematicInfoFile;
            If FileExists(SchInfoFile) Then
            Begin
                // Read the JSON to get the original schematic file path
                Try
                    AssignFile(F, SchInfoFile);
                    Reset(F);
                    While Not Eof(F) Do
                    Begin
                        ReadLn(F, Line);
                        If Pos('"file_name"', Line) > 0 Then
                        Begin
                            // Extract file name from JSON
                            I := Pos(':', Line);
                            If I > 0 Then
                            Begin
                                SchDocPath := Copy(Line, I + 1, Length(Line));
                                SchDocPath := RemoveChars(SchDocPath, '",');
                                SchDocPath := Trim(SchDocPath);
                                
                                // Try to find this file in the project
                                For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
                                Begin
                                    ProjDoc := Project.DM_LogicalDocuments(I);
                                    If ProjDoc <> Nil Then
                                    Begin
                                        If UpperCase(ExtractFileName(ProjDoc.DM_FullPath)) = UpperCase(SchDocPath) Then
                                        Begin
                                            Try
                                                TempServerDoc := Client.OpenDocument('SCH', ProjDoc.DM_FullPath);
                                                If TempServerDoc <> Nil Then
                                                Begin
                                                    Client.ShowDocument(TempServerDoc);
                                                    Sleep(2000);
                                                    Application.ProcessMessages;
                                                    Doc := SchServer.GetCurrentSchDocument;
                                                    If Doc <> Nil Then Break;
                                                End;
                                            Except
                                            End;
                                        End;
                                    End;
                                End;
                            End;
                            Break;
                        End;
                    End;
                    CloseFile(F);
                Except
                End;
            End;
        End;
        
        // Final check - if still no schematic, return error
        If Doc = Nil Then
        Begin
            WriteRes(False, 'No schematic open and no schematic found in project. Please open a schematic document in Altium first.');
            Exit;
        End;
    End;

    ProjectPath := ExtractFilePath(Project.DM_ProjectFullPath);
    SchDocPath := Doc.DocumentName;

    // ---------------------------------------------------------------
    // STEP 1: Create a NEW blank PCB document with unique name
    // ---------------------------------------------------------------
    BaseName := ChangeFileExt(ExtractFileName(SchDocPath), '');
    PCBDocPath := ProjectPath + BaseName + '.PcbDoc';
    Counter := 1;
    While FileExists(PCBDocPath) Do
    Begin
        PCBDocPath := ProjectPath + BaseName + '_' + IntToStr(Counter) + '.PcbDoc';
        Inc(Counter);
    End;
    NewPCBFileName := ExtractFileName(PCBDocPath);

    ResetParameters;
    AddStringParameter('ObjectKind', 'PCB');
    AddStringParameter('FileName', PCBDocPath);
    RunProcess('WorkspaceManager:OpenObject');
    Sleep(2000);
    Application.ProcessMessages;

    ServerDoc := Client.GetDocumentByPath(PCBDocPath);
    If ServerDoc = Nil Then
    Begin
        WriteRes(False, 'Failed to create PCB: ' + PCBDocPath);
        Exit;
    End;

    // ---------------------------------------------------------------
    // STEP 2: Add new PCB to the project, save PCB file, and save project
    // ---------------------------------------------------------------
    Project.DM_AddSourceDocument(PCBDocPath);
    
    // CRITICAL: Save the PCB file immediately so ECO can find it
    Try
        ServerDoc := Client.GetDocumentByPath(PCBDocPath);
        If ServerDoc <> Nil Then
        Begin
            ServerDoc.DoFileSave(PCBDocPath);
            Sleep(1000);
            Application.ProcessMessages;
        End;
    Except
    End;
    
    // Save the project file
    Try
        ServerDoc := Client.GetDocumentByPath(Project.DM_ProjectFullPath);
        If ServerDoc <> Nil Then
            ServerDoc.DoFileSave(Project.DM_ProjectFullPath);
    Except
    End;
    Sleep(1000);
    Application.ProcessMessages;

    // ---------------------------------------------------------------
    // STEP 3: Re-check schematic is still open (it should be from export)
    // ---------------------------------------------------------------
    Doc := SchServer.GetCurrentSchDocument;
    If Doc = Nil Then
    Begin
        // Try one more time to find and open schematic
        For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
        Begin
            ProjDoc := Project.DM_LogicalDocuments(I);
            If ProjDoc <> Nil Then
            Begin
                If (UpperCase(ExtractFileExt(ProjDoc.DM_FullPath)) = '.SCHDOC') Or
                   (UpperCase(ExtractFileExt(ProjDoc.DM_FullPath)) = '.SCH') Then
                Begin
                    Try
                        TempServerDoc := Client.OpenDocument('SCH', ProjDoc.DM_FullPath);
                        If TempServerDoc <> Nil Then
                        Begin
                            Client.ShowDocument(TempServerDoc);
                            Sleep(2000);
                            Application.ProcessMessages;
                            Doc := SchServer.GetCurrentSchDocument;
                            If Doc <> Nil Then Break;
                        End;
                    Except
                    End;
                End;
            End;
        End;
    End;
    
    // If still no schematic, return error
    If Doc = Nil Then
    Begin
        WriteRes(False, 'No schematic open. Please ensure the schematic is open in Altium before creating PCB.');
        Exit;
    End;

    // ---------------------------------------------------------------
    // STEP 4: Ensure schematic info is exported (contains all component/net data)
    // ---------------------------------------------------------------
    // CRITICAL: Export schematic info in silent mode (no result file written)
    // This prevents interfering with the create_pcb result
    Try
        SilentMode := True;
        ExportSchematicInfo;
        SilentMode := False;
        Sleep(1000);
    Except
    End;

    // ---------------------------------------------------------------
    // STEP 5: Build PCB directly from schematic data (NO ECO!)
    // Uses the exported schematic JSON to create components and nets directly
    // ---------------------------------------------------------------
    
    // Open PCB document
    ServerDoc := Client.OpenDocument('PCB', PCBDocPath);
    If ServerDoc <> Nil Then
    Begin
        Client.ShowDocument(ServerDoc);
        Sleep(1000);
        Application.ProcessMessages;
    End;
    
    // Build PCB directly from schematic data
    BuildPCBFromSchematicData;
    
    // Verify component count
    CompCount := 0;
    Board := PCBServer.GetCurrentPCBBoard;
    If Board <> Nil Then
    Begin
        BoardFileName := ExtractFileName(Board.FileName);
        If BoardFileName = NewPCBFileName Then
        Begin
            Try
                Iter := Board.BoardIterator_Create;
                Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
                Iter.AddFilter_LayerSet(AllLayers);
                Comp := Iter.FirstPCBObject;
                While Comp <> Nil Do
                Begin
                    Inc(CompCount);
                    Comp := Iter.NextPCBObject;
                End;
                Board.BoardIterator_Destroy(Iter);
            Except
            End;
        End;
    End;
    
    // Return result
    If CompCount > 0 Then
        WriteRes(True, 'PCB_BUILT|' + IntToStr(CompCount) + '|' + PCBDocPath)
    Else
        WriteRes(True, 'PCB_EMPTY|0|' + PCBDocPath);
End;

{..............................................................................}
{ RUN ECO - Transfer schematic data to PCB (separate retry command)            }
{ Call this after the user has manually approved the ECO dialog                 }
{..............................................................................}
Procedure RunECOTransfer;
Var
    Board : IPCB_Board;
    CompCount : Integer;
    Iter : IPCB_BoardIterator;
    Comp : IPCB_Component;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open. Open the target PCB first.');
        Exit;
    End;

    CompCount := 0;
    Try
        // Count components using iterator (correct Altium API method)
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
        Iter.AddFilter_LayerSet(AllLayers);
        Comp := Iter.FirstPCBObject;
        While Comp <> Nil Do
        Begin
            Inc(CompCount);
            Comp := Iter.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iter);
    Except
    End;

    If CompCount > 0 Then
        WriteRes(True, 'ECO_OK|' + IntToStr(CompCount) + '|' + Board.FileName)
    Else
        WriteRes(True, 'ECO_EMPTY|0|' + Board.FileName);
End;

{..............................................................................}
{ AUTO-PLACE COMPONENTS on PCB                                                 }
{..............................................................................}
Procedure AutoPlaceComponents;
Var
    Board : IPCB_Board;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open for auto-placement');
        Exit;
    End;

    Try
        // Use Altium's auto-placer
        ResetParameters;
        AddStringParameter('Mode', 'ClusterPlacer');
        RunProcess('PCB:AutoPlacer');

        Sleep(3000);

        // Refresh the board
        Try
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
        Except
        End;

        WriteRes(True, 'Auto-placement completed');
    Except
        WriteRes(False, 'Auto-placement failed');
    End;
End;

{..............................................................................}
{ AUTO-ROUTE PCB                                                               }
{..............................................................................}
Procedure AutoRoute;
Var
    Board : IPCB_Board;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open for auto-routing');
        Exit;
    End;

    Try
        // Use Altium's auto-router
        ResetParameters;
        AddStringParameter('RouteAll', 'True');
        RunProcess('PCB:RunAutoRouter');

        Sleep(5000);

        // Refresh the board
        Try
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
        Except
        End;

        WriteRes(True, 'Auto-routing completed');
    Except
        WriteRes(False, 'Auto-routing failed. Try interactive routing or a different router.');
    End;
End;

{..............................................................................}
{ EXPORT PCB INFO (after PCB is created)                                       }
{..............................................................................}
Procedure ExportNewPCBInfo;
Var
    Board : IPCB_Board;
    Comp : IPCB_Component;
    Net : IPCB_Net;
    Track : IPCB_Track;
    Via : IPCB_Via;
    Iter : IPCB_BoardIterator;
    F : TextFile;
    Q, FinalPath, TempFilePath : String;
    N, CompCount, NetCount, TrackCount, ViaCount : Integer;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open');
        Exit;
    End;

    Q := Chr(34);
    If BasePath = '' Then BasePath := GetBasePath;

    FinalPath := BasePath + 'PCB_Project\altium_pcb_info.json';
    TempFilePath := 'C:\Windows\Temp\pcb_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';

    Try
        AssignFile(F, TempFilePath);
        Rewrite(F);
    Except
        WriteRes(False, 'Cannot write to temp directory');
        Exit;
    End;

    // Start JSON
    WriteLn(F, Chr(123));
    WriteLn(F, Q + 'export_source' + Q + ':' + Q + 'altium_designer' + Q + ',');
    WriteLn(F, Q + 'file_name' + Q + ':' + Q + EscapeJSONString(Board.FileName) + Q + ',');

    // Board dimensions
    WriteLn(F, Q + 'board_size' + Q + ':' + Chr(123));
    Try
        WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Right - Board.BoardOutline.BoundingRectangle.Left)) + ',');
        WriteLn(F, Q + 'height_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Top - Board.BoardOutline.BoundingRectangle.Bottom)));
    Except
        WriteLn(F, Q + 'width_mm' + Q + ':100,');
        WriteLn(F, Q + 'height_mm' + Q + ':80');
    End;
    WriteLn(F, Chr(125) + ',');

    // Components
    WriteLn(F, Q + 'components' + Q + ':[');
    CompCount := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
    Iter.AddFilter_LayerSet(AllLayers);

    Comp := Iter.FirstPCBObject;
    While Comp <> Nil Do
    Begin
        If CompCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'designator' + Q + ':' + Q + Comp.Name.Text + Q + ',');
        WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Comp.X)) + ',');
        WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Comp.Y)) + ',');
        WriteLn(F, Q + 'rotation' + Q + ':' + FloatToStr(Comp.Rotation) + ',');
        WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Comp.Layer) + Q + ',');
        WriteLn(F, Q + 'footprint' + Q + ':' + Q + Comp.Pattern + Q);
        Write(F, Chr(125));
        Inc(CompCount);
        Comp := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    WriteLn(F, '],');

    // Nets
    WriteLn(F, Q + 'nets' + Q + ':[');
    NetCount := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eNetObject));
    Iter.AddFilter_LayerSet(AllLayers);

    Net := Iter.FirstPCBObject;
    While Net <> Nil Do
    Begin
        If NetCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + EscapeJSONString(Net.Name) + Q);
        Write(F, Chr(125));
        Inc(NetCount);
        Net := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    WriteLn(F, '],');

    // Tracks
    WriteLn(F, Q + 'tracks' + Q + ':[');
    TrackCount := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eTrackObject));
    Iter.AddFilter_LayerSet(AllLayers);

    Track := Iter.FirstPCBObject;
    While Track <> Nil Do
    Begin
        If TrackCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'x1_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.X1)) + ',');
        WriteLn(F, Q + 'y1_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Y1)) + ',');
        WriteLn(F, Q + 'x2_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.X2)) + ',');
        WriteLn(F, Q + 'y2_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Y2)) + ',');
        WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Width)) + ',');
        WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Track.Layer) + Q);
        Write(F, Chr(125));
        Inc(TrackCount);
        Track := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    WriteLn(F, '],');

    // Vias
    WriteLn(F, Q + 'vias' + Q + ':[');
    ViaCount := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eViaObject));
    Iter.AddFilter_LayerSet(AllLayers);

    Via := Iter.FirstPCBObject;
    While Via <> Nil Do
    Begin
        If ViaCount > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.X)) + ',');
        WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.Y)) + ',');
        WriteLn(F, Q + 'hole_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.HoleSize)) + ',');
        WriteLn(F, Q + 'diameter_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.Size)));
        Write(F, Chr(125));
        Inc(ViaCount);
        Via := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    WriteLn(F, '],');

    // Statistics
    WriteLn(F, Q + 'statistics' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'component_count' + Q + ':' + IntToStr(CompCount) + ',');
    WriteLn(F, Q + 'net_count' + Q + ':' + IntToStr(NetCount) + ',');
    WriteLn(F, Q + 'track_count' + Q + ':' + IntToStr(TrackCount) + ',');
    WriteLn(F, Q + 'via_count' + Q + ':' + IntToStr(ViaCount));
    WriteLn(F, Chr(125));

    WriteLn(F, Chr(125));
    CloseFile(F);

    // Move temp file to final location
    Try
        If FileExists(FinalPath) Then DeleteFile(FinalPath);
        RenameFile(TempFilePath, FinalPath);
    Except
        Try
            CopyFile(TempFilePath, FinalPath);
            DeleteFile(TempFilePath);
        Except
        End;
    End;

    WriteRes(True, 'PCB info exported: ' + IntToStr(CompCount) + ' components, ' +
             IntToStr(NetCount) + ' nets, ' + IntToStr(TrackCount) + ' tracks');
End;

{..............................................................................}
{ PROCESS COMMAND                                                              }
{..............................................................................}
Procedure ProcessCommand;
Var
    Cmd, Act : String;
Begin
    Cmd := ReadCmd;
    If Length(Cmd) < 5 Then Exit;

    // Clear the command file immediately to prevent re-processing
    ClearCmd;

    Act := ParseValue(Cmd, 'action');
    CurrentAction := Act;

    If Act = '' Then
    Begin
        WriteRes(False, 'No action specified');
        Exit;
    End;

    // PING
    If Act = 'ping' Then
    Begin
        WriteRes(True, 'Schematic server alive');
    End

    // EXPORT SCHEMATIC INFO
    Else If Act = 'export_schematic_info' Then
    Begin
        Try
            SilentMode := False; // Keep SilentMode False so errors are reported
            ExportSchematicInfo;
            // ExportSchematicInfo calls WriteRes, so result is already written
        Except
            // Simple exception handling - DelphiScript doesn't support typed exceptions
            WriteRes(False, 'Error exporting schematic info');
        End;
    End

    // CREATE PCB FROM SCHEMATIC
    Else If Act = 'create_pcb' Then
    Begin
        // CRITICAL: Clear any stale result file before starting
        // This prevents reading old export_schematic_info results
        Try
            If FileExists(GetResultFile) Then
            Begin
                DeleteFile(GetResultFile);
                Sleep(200); // Give filesystem time to process
            End;
        Except
        End;
        CreatePCBFromSchematic;
    End

    // CHECK ECO STATUS (after manual ECO)
    Else If Act = 'check_eco' Then
    Begin
        RunECOTransfer;
    End

    // AUTO-PLACE COMPONENTS
    Else If Act = 'auto_place' Then
    Begin
        AutoPlaceComponents;
    End

    // AUTO-ROUTE
    Else If Act = 'auto_route' Then
    Begin
        AutoRoute;
    End

    // EXPORT PCB INFO (after PCB creation)
    Else If Act = 'export_pcb_info' Then
    Begin
        SilentMode := True;
        ExportNewPCBInfo;
        SilentMode := False;
    End

    // CREATE PCB LIBRARIES
    Else If Act = 'create_libraries' Then
    Begin
        Try
            CreatePCBLibraries;
        Except
            WriteRes(False, 'Error creating PCB libraries');
        End;
    End

    // UNKNOWN
    Else
    Begin
        WriteRes(False, 'Unknown action: ' + Act);
    End;
End;

{..............................................................................}
{ START SERVER - Polling Loop                                                  }
{..............................................................................}
Procedure StartServer;
Var
    Doc : ISch_Document;
    CmdFile, ResFile : String;
Begin
    ServerRunning := True;
    SilentMode := False;
    CurrentAction := '';

    // Initialize base path
    BasePath := GetBasePath;

    CmdFile := GetCommandFile;
    ResFile := GetResultFile;

    Doc := SchServer.GetCurrentSchDocument;

    If Doc = Nil Then
    Begin
        ShowMessage('EagilinsED Schematic Server Started!' + #13#10 +
                    'No schematic open. Please open a schematic file.' + #13#10 +
                    #13#10 +
                    'Command file: ' + CmdFile + #13#10 +
                    'Result file: ' + ResFile);
    End
    Else
    Begin
        ShowMessage('EagilinsED Schematic Server Started!' + #13#10 +
                    'Auto-exporting schematic info...' + #13#10 +
                    #13#10 +
                    'Schematic: ' + Doc.DocumentName + #13#10 +
                    'Command file: ' + CmdFile + #13#10 +
                    'Result file: ' + ResFile);
        ExportSchematicInfo;
    End;

    // Polling loop
    While ServerRunning Do
    Begin
        Try
            ProcessCommand;
        Except
        End;
        Sleep(200);
        Application.ProcessMessages;
    End;

    ShowMessage('Schematic Server Stopped.');
End;

{..............................................................................}
{ STOP SERVER                                                                  }
{..............................................................................}
Procedure StopServer;
Begin
    ServerRunning := False;
    ShowMessage('Server stopped.');
End;

End.
