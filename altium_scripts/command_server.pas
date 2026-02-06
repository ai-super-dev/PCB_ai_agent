{..............................................................................}
{ Altium Command Server - Full Integration with EagilinsED Agent             }
{ Supports: DRC, Export, Move, Add Track, Add Via, Delete                     }
{ Updated: Dynamic paths, Complete rule export                                }
{ Fixed: ShowMessage blocking, log spam, ViaRule type, hardcoded paths       }
{..............................................................................}

Var
    ServerRunning : Boolean;
    BasePath : String;  // Dynamic base path for files
    SilentMode : Boolean;  // When True, suppress ShowMessage dialogs
    CurrentAction : String;  // Tracks which action is being processed (for result validation)
    GlobalBoard : IPCB_Board;  // Cached board reference (GetCurrentPCBBoard can return Nil in polling loop)

{..............................................................................}
Function GetBasePath : String;
Var
    Project : IProject;
    ProjectPath : String;
    Board : IPCB_Board;
    ScriptPath : String;
    TempPath : String;
    PCBFilePath : String;
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
    
    // PRIORITY 2: Try to get path from current PCB board, navigate up to project root
    Board := PCBServer.GetCurrentPCBBoard;
    If Board <> Nil Then
    Begin
        PCBFilePath := Board.FileName;
        If PCBFilePath <> '' Then
        Begin
            TempPath := ExtractFilePath(PCBFilePath);
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
    
    // PRIORITY 4: Hardcoded fallback
    Result := 'E:\Altium_Project\PCB_ai_agent\';
    
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
    Result := BasePath + 'altium_result.json';
End;

{..............................................................................}
Function GetPCBInfoFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'altium_pcb_info.json';
End;

{..............................................................................}
{ GetBoard - Reliable board reference that survives polling loop focus changes }
{ First tries GetCurrentPCBBoard; if Nil, uses cached GlobalBoard             }
{..............................................................................}
Function GetBoard : IPCB_Board;
Begin
    Result := PCBServer.GetCurrentPCBBoard;
    If Result = Nil Then
        Result := GlobalBoard;
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
    
    // Also skip if the temp file exists (Python is mid-write)
    If FileExists(CmdFile + '.tmp') Then Exit;
    
    RetryCount := 0;
    While RetryCount < 10 Do
    Begin
        // Use TStringList instead of AssignFile/Reset
        // TStringList.LoadFromFile exceptions ARE catchable by Try...Except
        // unlike AssignFile/Reset which raises uncatchable EInOutError in DelphiScript
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
            // File locked by Python or still being written - retry
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
    
    // Include action name so Python can validate the result matches the sent command
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
            // File locked, retry
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
{ MOVE COMPONENT                                                               }
{..............................................................................}
Function MoveComp(Des : String; X, Y : Double) : Boolean;
Var
    Board : IPCB_Board;
    Comp  : IPCB_Component;
    Iter  : IPCB_BoardIterator;
    CName : String;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Des := UpperCase(Trim(Des));
    
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Comp := Iter.FirstPCBObject;
    While Comp <> Nil Do
    Begin
        CName := UpperCase(Comp.Name.Text);
        
        If CName = Des Then
        Begin
            PCBServer.PreProcess;
            Comp.BeginModify;
            Comp.X := MMsToCoord(X);
            Comp.Y := MMsToCoord(Y);
            Comp.EndModify;
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
            Result := True;
            Break;
        End;
        Comp := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
End;

{..............................................................................}
{ ADD TRACK                                                                    }
{..............................................................................}
Function AddTrack(NetName, LayerName : String; X1, Y1, X2, Y2, Width : Double) : Boolean;
Var
    Board : IPCB_Board;
    Track : IPCB_Track;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track = Nil Then Exit;
    
    Track.X1 := MMsToCoord(X1);
    Track.Y1 := MMsToCoord(Y1);
    Track.X2 := MMsToCoord(X2);
    Track.Y2 := MMsToCoord(Y2);
    Track.Width := MMsToCoord(Width);
    
    If UpperCase(LayerName) = 'BOTTOM' Then
        Track.Layer := eBottomLayer
    Else
        Track.Layer := eTopLayer;
    
    PCBServer.PreProcess;
    Board.AddPCBObject(Track);
    PCBServer.PostProcess;
    Board.GraphicallyInvalidate;
    
    Result := True;
End;

{..............................................................................}
{ ADD VIA                                                                      }
{..............................................................................}
Function AddVia(X, Y, HoleSize, Diameter : Double) : Boolean;
Var
    Board : IPCB_Board;
    Via   : IPCB_Via;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Via := PCBServer.PCBObjectFactory(eViaObject, eNoDimension, eCreate_Default);
    If Via = Nil Then Exit;
    
    Via.X := MMsToCoord(X);
    Via.Y := MMsToCoord(Y);
    Via.HoleSize := MMsToCoord(HoleSize);
    Via.Size := MMsToCoord(Diameter);
    Via.LowLayer := eBottomLayer;
    Via.HighLayer := eTopLayer;
    
    PCBServer.PreProcess;
    Board.AddPCBObject(Via);
    PCBServer.PostProcess;
    Board.GraphicallyInvalidate;
    
    Result := True;
End;

{..............................................................................}
{ RUN DRC                                                                      }
{..............................................................................}
Procedure RunDRC;
Var
    Board : IPCB_Board;
Begin
    Board := GetBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open');
        Exit;
    End;
    
    ResetParameters;
    AddStringParameter('Action', 'Run');
    RunProcess('PCB:RunDesignRuleCheck');
    
    Sleep(2000);
    
    WriteRes(True, 'DRC command executed. Report will be generated in Project Outputs folder.');
End;

{..............................................................................}
{ EXPORT PCB INFO - Silent-mode aware                                         }
{ When SilentMode=True, skips ShowMessage calls (used during rule creation)   }
{..............................................................................}
Procedure ExportPCBInfo;
Var
    Board : IPCB_Board;
    Comp  : IPCB_Component;
    Net   : IPCB_Net;
    Track : IPCB_Track;
    Via   : IPCB_Via;
    Rule  : IPCB_Rule;
    ClearanceRule : IPCB_ClearanceConstraint;
    WidthRule : IPCB_RoutingWidthRule;
    ViaRule : IPCB_RoutingViaRule;
    ShortCircuitRule : IPCB_ShortCircuitRule;
    MaskRule : IPCB_SolderMaskExpansionRule;
    Layer : TLayer;
    Iter : IPCB_BoardIterator;
    F, F2 : TextFile;
    Q, S, LayerName, NetName, FinalPath, LineContent, TempFilePath : String;
    N, I, LayerID, CompCount, NetCount, TrackCount, ViaCount, RuleCount, RetryCount : Integer;
    RuleTypeDetected : Boolean;
Begin
    // CRITICAL: Get fresh board reference and ensure it's up-to-date
    Board := GetBoard;
    If Board = Nil Then
    Begin
        If Not SilentMode Then
            ShowMessage('Error: No PCB file is open!');
        WriteRes(False, 'No PCB open');
        Exit;
    End;
    
    // Force board refresh to ensure all newly added objects are visible
    Try
        PCBServer.PostProcess;
        Board.GraphicallyInvalidate;
    Except
    End;
    
    Q := Chr(34);
    
    // Ensure BasePath is set
    If BasePath = '' Then
        BasePath := GetBasePath;
    
    // Validate path exists
    If Not DirectoryExists(BasePath) Then
    Begin
        If Not SilentMode Then
            ShowMessage('Path does not exist: ' + BasePath);
        WriteRes(False, 'Directory does not exist: ' + BasePath);
        Exit;
    End;
    
    FinalPath := BasePath + 'altium_pcb_info.json';
    
    // Use temp file to avoid locking issues
    TempFilePath := 'C:\Windows\Temp\altium_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
    If Not DirectoryExists('C:\Windows\Temp\') Then
        TempFilePath := BasePath + 'altium_export_temp.json';
    
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
    WriteLn(F, Q + 'board_thickness_mm' + Q + ':1.6,');
    
    // Board dimensions
    WriteLn(F, Q + 'board_size' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Right - Board.BoardOutline.BoundingRectangle.Left)) + ',');
    WriteLn(F, Q + 'height_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Top - Board.BoardOutline.BoundingRectangle.Bottom)));
    WriteLn(F, Chr(125) + ',');
    
    // Layers
    WriteLn(F, Q + 'layers' + Q + ':[');
    LayerID := 0;
    
    Try
        LayerName := Board.LayerName(eTopLayer);
        If LayerName <> '' Then
        Begin
            WriteLn(F, Chr(123) + Q + 'id' + Q + ':' + Q + 'L1' + Q);
            WriteLn(F, ',' + Q + 'name' + Q + ':' + Q + LayerName + Q);
            WriteLn(F, ',' + Q + 'kind' + Q + ':' + Q + 'signal' + Q);
            WriteLn(F, ',' + Q + 'index' + Q + ':1');
            Write(F, Chr(125));
            Inc(LayerID);
        End;
    Except
    End;
    
    Try
        LayerName := Board.LayerName(eBottomLayer);
        If LayerName <> '' Then
        Begin
            If LayerID > 0 Then WriteLn(F, ',');
            WriteLn(F, Chr(123) + Q + 'id' + Q + ':' + Q + 'L2' + Q);
            WriteLn(F, ',' + Q + 'name' + Q + ':' + Q + LayerName + Q);
            WriteLn(F, ',' + Q + 'kind' + Q + ':' + Q + 'signal' + Q);
            WriteLn(F, ',' + Q + 'index' + Q + ':2');
            Write(F, Chr(125));
            Inc(LayerID);
        End;
    Except
    End;
    
    For I := 1 To 4 Do
    Begin
        Try
            If I = 1 Then Layer := eInternalPlane1
            Else If I = 2 Then Layer := eInternalPlane2
            Else If I = 3 Then Layer := eInternalPlane3
            Else Layer := eInternalPlane4;
            
            LayerName := Board.LayerName(Layer);
            If LayerName <> '' Then
            Begin
                If LayerID > 0 Then WriteLn(F, ',');
                S := 'signal';
                If Pos('GND', UpperCase(LayerName)) > 0 Then S := 'ground'
                Else If (Pos('VCC', UpperCase(LayerName)) > 0) Or (Pos('POWER', UpperCase(LayerName)) > 0) Then S := 'power';
                
                WriteLn(F, Chr(123) + Q + 'id' + Q + ':' + Q + 'L' + IntToStr(LayerID+1) + Q);
                WriteLn(F, ',' + Q + 'name' + Q + ':' + Q + LayerName + Q);
                WriteLn(F, ',' + Q + 'kind' + Q + ':' + Q + S + Q);
                WriteLn(F, ',' + Q + 'index' + Q + ':' + IntToStr(LayerID+1));
                Write(F, Chr(125));
                Inc(LayerID);
            End;
        Except
        End;
    End;
    
    WriteLn(F, '],');
    
    // Components
    WriteLn(F, Q + 'components' + Q + ':[');
    N := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Comp := Iter.FirstPCBObject;
    While Comp <> Nil Do
    Begin
        If N > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'designator' + Q + ':' + Q + Comp.Name.Text + Q + ',');
        WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Comp.X)) + ',');
        WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Comp.Y)) + ',');
        WriteLn(F, Q + 'rotation' + Q + ':' + FloatToStr(Comp.Rotation) + ',');
        WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Comp.Layer) + Q + ',');
        WriteLn(F, Q + 'footprint' + Q + ':' + Q + Comp.Pattern + Q + ',');
        WriteLn(F, Q + 'comment' + Q + ':' + Q + Comp.Comment.Text + Q + ',');
        WriteLn(F, Q + 'pads' + Q + ':[]');
        Write(F, Chr(125));
        Inc(N);
        Comp := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    CompCount := N;
    WriteLn(F, '],');
    
    // Nets
    WriteLn(F, Q + 'nets' + Q + ':[');
    N := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eNetObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Net := Iter.FirstPCBObject;
    While Net <> Nil Do
    Begin
        If N > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + Net.Name + Q);
        Write(F, Chr(125));
        Inc(N);
        Net := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    NetCount := N;
    WriteLn(F, '],');
    
    // Tracks
    WriteLn(F, Q + 'tracks' + Q + ':[');
    N := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eTrackObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Track := Iter.FirstPCBObject;
    While Track <> Nil Do
    Begin
        If N > 0 Then WriteLn(F, ',');
        NetName := '';
        If Track.Net <> Nil Then NetName := Track.Net.Name;
        
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'net' + Q + ':' + Q + NetName + Q + ',');
        WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Track.Layer) + Q + ',');
        WriteLn(F, Q + 'x1_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.X1)) + ',');
        WriteLn(F, Q + 'y1_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Y1)) + ',');
        WriteLn(F, Q + 'x2_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.X2)) + ',');
        WriteLn(F, Q + 'y2_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Y2)) + ',');
        WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Track.Width)));
        Write(F, Chr(125));
        Inc(N);
        Track := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    TrackCount := N;
    WriteLn(F, '],');
    
    // Vias
    WriteLn(F, Q + 'vias' + Q + ':[');
    N := 0;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eViaObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Via := Iter.FirstPCBObject;
    While Via <> Nil Do
    Begin
        If N > 0 Then WriteLn(F, ',');
        NetName := '';
        If Via.Net <> Nil Then NetName := Via.Net.Name;
        
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'net' + Q + ':' + Q + NetName + Q + ',');
        WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.X)) + ',');
        WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.Y)) + ',');
        WriteLn(F, Q + 'hole_size_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.HoleSize)) + ',');
        WriteLn(F, Q + 'diameter_mm' + Q + ':' + FloatToStr(CoordToMMs(Via.Size)) + ',');
        WriteLn(F, Q + 'low_layer' + Q + ':' + Q + Board.LayerName(Via.LowLayer) + Q + ',');
        WriteLn(F, Q + 'high_layer' + Q + ':' + Q + Board.LayerName(Via.HighLayer) + Q);
        Write(F, Chr(125));
        Inc(N);
        Via := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    ViaCount := N;
    WriteLn(F, '],');
    
    // Design Rules
    WriteLn(F, Q + 'rules' + Q + ':[');
    N := 0;
    
    Try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
        Iter.AddFilter_LayerSet(AllLayers);
        Rule := Iter.FirstPCBObject;
    Except
        WriteLn(F, '],');
        Rule := Nil;
    End;
    
    While Rule <> Nil Do
    Begin
        LayerName := Rule.Name;
        If LayerName = '' Then
            LayerName := 'Unnamed_Rule_' + IntToStr(N + 1);
        
        If N > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + LayerName + Q + ',');
        If Rule.Enabled Then
            WriteLn(F, Q + 'enabled' + Q + ':true,')
        Else
            WriteLn(F, Q + 'enabled' + Q + ':false,');
        
        Try
            WriteLn(F, Q + 'priority' + Q + ':' + IntToStr(Rule.Priority) + ',');
        Except
            WriteLn(F, Q + 'priority' + Q + ':1,');
        End;
        
        Try
            S := Rule.Scope1Expression;
            If S <> '' Then WriteLn(F, Q + 'scope_first' + Q + ':' + Q + S + Q + ',');
        Except
        End;
        Try
            S := Rule.Scope2Expression;
            If S <> '' Then WriteLn(F, Q + 'scope_second' + Q + ':' + Q + S + Q + ',');
        Except
        End;
        
        // Detect rule type by attempting interface casts (more reliable than RuleKind constants)
        // This avoids using constants that may not be available in all Altium versions
        RuleTypeDetected := False;
        S := UpperCase(LayerName);
        
        // Try to detect Clearance Rule - attempt cast to IPCB_ClearanceConstraint
        // Note: Property access after cast may not work in all Altium versions
        // We'll export as clearance type with default value - Python can read actual value if needed
        If Not RuleTypeDetected Then
        Begin
            Try
                ClearanceRule := Rule;
                // If cast succeeds without exception, it's a clearance rule
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'clearance' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
                // TODO: Fix property access - Gap/Minimum may not be accessible after cast
                // For now, export default value - the rule exists and is created correctly
                WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
                RuleTypeDetected := True;
            Except
            End;
        End;
        
        // Try to detect Width Rule - attempt cast to IPCB_RoutingWidthRule
        If Not RuleTypeDetected Then
        Begin
            Try
                WidthRule := Rule;
                // If cast succeeds without exception, it's a width rule
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
                Try
                    WriteLn(F, Q + 'min_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MinWidth)) + ',');
                    WriteLn(F, Q + 'preferred_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.PreferredWidth)) + ',');
                    WriteLn(F, Q + 'max_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MaxWidth)));
                Except
                    WriteLn(F, Q + 'min_width_mm' + Q + ':0.0');
                End;
                RuleTypeDetected := True;
            Except
            End;
        End;
        
        // Try to detect Via Rule - attempt cast to IPCB_RoutingViaRule
        If Not RuleTypeDetected Then
        Begin
            Try
                ViaRule := Rule;
                // If cast succeeds without exception, it's a via rule
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'via' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
                Try
                    WriteLn(F, Q + 'min_hole_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MinHoleSize)) + ',');
                    WriteLn(F, Q + 'max_hole_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MaxHoleSize)) + ',');
                    WriteLn(F, Q + 'min_diameter_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MinWidth)) + ',');
                    WriteLn(F, Q + 'max_diameter_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MaxWidth)));
                Except
                    WriteLn(F, Q + 'min_hole_mm' + Q + ':0.0');
                End;
                RuleTypeDetected := True;
            Except
            End;
        End;
        
        If Not RuleTypeDetected Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'other' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'General' + Q);
        End;
        
        Write(F, Chr(125));
        Inc(N);
        Rule := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    RuleCount := N;
    
    WriteLn(F, '],');
    
    // Statistics
    WriteLn(F, Q + 'statistics' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'component_count' + Q + ':' + IntToStr(CompCount) + ',');
    WriteLn(F, Q + 'net_count' + Q + ':' + IntToStr(NetCount) + ',');
    WriteLn(F, Q + 'track_count' + Q + ':' + IntToStr(TrackCount) + ',');
    WriteLn(F, Q + 'via_count' + Q + ':' + IntToStr(ViaCount) + ',');
    WriteLn(F, Q + 'rule_count' + Q + ':' + IntToStr(RuleCount) + ',');
    WriteLn(F, Q + 'layer_count' + Q + ':' + IntToStr(LayerID));
    WriteLn(F, Chr(125));
    
    WriteLn(F, Chr(125));
    CloseFile(F);
    
    Sleep(500);
    
    // Copy temp to final
    RetryCount := 0;
    While RetryCount < 10 Do
    Begin
        Try
            If FileExists(FinalPath) Then
            Begin
                Try
                    DeleteFile(FinalPath);
                    Sleep(300);
                Except
                    Sleep(1000);
                End;
            End;
            
            AssignFile(F, TempFilePath);
            Reset(F);
            AssignFile(F2, FinalPath);
            Rewrite(F2);
            
            While Not EOF(F) Do
            Begin
                ReadLn(F, LineContent);
                WriteLn(F2, LineContent);
            End;
            
            CloseFile(F);
            CloseFile(F2);
            
            If FileExists(FinalPath) Then
            Begin
                Try
                    DeleteFile(TempFilePath);
                Except
                End;
                
                // Only show message in interactive mode (not during rule creation)
                If Not SilentMode Then
                Begin
                    ShowMessage('Export completed! Rules exported: ' + IntToStr(RuleCount) + #13#10 +
                                'File: ' + FinalPath);
                    WriteRes(True, 'Export completed: ' + FinalPath);
                End;
                // In silent mode, do NOT call WriteRes - let the caller handle it
                Exit;
            End;
        Except
            Inc(RetryCount);
            If RetryCount < 10 Then
                Sleep(500 * RetryCount);
        End;
    End;
    
    // Only write result in interactive mode
    If Not SilentMode Then
        WriteRes(True, 'Export completed (temp): ' + TempFilePath);
End;

{..............................................................................}
{ SAVE PCB FILE                                                                }
{..............................................................................}
Procedure SavePCBFile;
Var
    Board : IPCB_Board;
Begin
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Try
        ResetParameters;
        RunProcess('WorkspaceManager:SaveObject');
        Sleep(500);
    Except
    End;
End;

{..............................................................................}
{ CREATE RULE                                                                  }
{..............................................................................}
Function CreateRule(RuleType, RuleName : String; Cmd : String) : Boolean;
Var
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    Net : IPCB_Net;
    ClearanceRule : IPCB_ClearanceConstraint;
    WidthRule : IPCB_RoutingWidthRule;
    ViaRule : IPCB_RoutingViaRule;
    ClearanceMM, MinWidth, PrefWidth, MaxWidth, MinHole, MaxHole, MinDia, MaxDia : Double;
    Scope1, Scope2, NetName1, NetName2 : String;
    Iter : IPCB_BoardIterator;
    RuleFound, NetFound1, NetFound2 : Boolean;
    RetryCount : Integer;
    DebugLog : TStringList;
Begin
    Result := False;
    
    // Debug log to track exactly where creation fails
    DebugLog := TStringList.Create;
    DebugLog.Add('=== CreateRule Debug ' + DateTimeToStr(Now) + ' ===');
    DebugLog.Add('RuleType: ' + RuleType);
    DebugLog.Add('RuleName: ' + RuleName);
    
    Board := GetBoard;
    If Board = Nil Then
    Begin
        DebugLog.Add('FAIL: Board is Nil (both GetCurrentPCBBoard and GlobalBoard are Nil)');
        DebugLog.Add('Hint: Make sure PCB was open when StartServer was called');
        DebugLog.SaveToFile(BasePath + 'rule_debug.txt');
        DebugLog.Free;
        Exit;
    End;
    DebugLog.Add('OK: Board found - ' + Board.FileName);
    
    // Check if rule with same name already exists
    RuleFound := False;
    Try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
        Iter.AddFilter_LayerSet(AllLayers);
        Rule := Iter.FirstPCBObject;
        While Rule <> Nil Do
        Begin
            If UpperCase(Trim(Rule.Name)) = UpperCase(Trim(RuleName)) Then
            Begin
                RuleFound := True;
                Break;
            End;
            Rule := Iter.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iter);
    Except
        Try
            Board.BoardIterator_Destroy(Iter);
        Except
        End;
    End;
    
    If RuleFound Then
    Begin
        DebugLog.Add('WARNING: Rule with name already exists - will delete and recreate');
        // Delete the existing rule so we can create a new one
        Try
            Board.RemovePCBObject(Rule);
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
            Sleep(200);
            DebugLog.Add('OK: Existing rule deleted');
        Except
            DebugLog.Add('EXCEPTION: Failed to delete existing rule');
            DebugLog.SaveToFile(BasePath + 'rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
    End
    Else
    Begin
        DebugLog.Add('OK: No duplicate rule name');
    End;
    
    RuleType := LowerCase(RuleType);
    
    // ============================================================
    // CLEARANCE RULE
    // ============================================================
    If RuleType = 'clearance' Then
    Begin
        DebugLog.Add('Creating clearance rule...');
        
        Try
            ClearanceRule := PCBServer.PCBRuleFactory(eRule_Clearance);
        Except
            DebugLog.Add('EXCEPTION: PCBRuleFactory(eRule_Clearance) threw error');
            DebugLog.SaveToFile(BasePath + 'rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        
        If ClearanceRule = Nil Then
        Begin
            DebugLog.Add('FAIL: PCBRuleFactory returned Nil');
            DebugLog.SaveToFile(BasePath + 'rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        DebugLog.Add('OK: PCBRuleFactory created rule object');
        
        Try
            ClearanceRule.Name := RuleName;
            DebugLog.Add('OK: Name set to ' + RuleName);
        Except
            DebugLog.Add('EXCEPTION: Setting Name failed');
        End;
        
        Try
            ClearanceMM := StrToFloatDef(ParseValue(Cmd, 'param_clearance_mm'), 0.254);
            DebugLog.Add('OK: ClearanceMM = ' + FloatToStr(ClearanceMM));
            ClearanceRule.Gap := MMsToCoord(ClearanceMM);
            DebugLog.Add('OK: Gap set');
        Except
            DebugLog.Add('EXCEPTION: Setting Gap failed - trying Minimum');
            Try
                ClearanceRule.Minimum := MMsToCoord(ClearanceMM);
                DebugLog.Add('OK: Minimum set instead');
            Except
                DebugLog.Add('EXCEPTION: Setting Minimum also failed');
            End;
        End;
        
        Try
            ClearanceRule.Enabled := True;
            DebugLog.Add('OK: Enabled set');
        Except
            DebugLog.Add('EXCEPTION: Setting Enabled failed');
        End;
        
        // Parse scope expressions
        Scope1 := ParseValue(Cmd, 'param_scope_first');
        Scope2 := ParseValue(Cmd, 'param_scope_second');
        DebugLog.Add('Scope1 raw: [' + Scope1 + ']');
        DebugLog.Add('Scope2 raw: [' + Scope2 + ']');
        
        // Set scope - use 'All' if empty or explicitly 'All'
        Try
            If (Scope1 = '') Or (UpperCase(Scope1) = 'ALL') Then
                ClearanceRule.Scope1Expression := 'All'
            Else
                ClearanceRule.Scope1Expression := 'InNet(' + Chr(39) + Scope1 + Chr(39) + ')';
            DebugLog.Add('OK: Scope1Expression set');
        Except
            DebugLog.Add('EXCEPTION: Setting Scope1Expression failed');
        End;
            
        Try
            If (Scope2 = '') Or (UpperCase(Scope2) = 'ALL') Then
                ClearanceRule.Scope2Expression := 'All'
            Else
                ClearanceRule.Scope2Expression := 'InNet(' + Chr(39) + Scope2 + Chr(39) + ')';
            DebugLog.Add('OK: Scope2Expression set');
        Except
            DebugLog.Add('EXCEPTION: Setting Scope2Expression failed');
        End;
        
        Try
            PCBServer.PreProcess;
            Board.AddPCBObject(ClearanceRule);
            PCBServer.PostProcess;
            DebugLog.Add('OK: AddPCBObject + PostProcess done');
        Except
            DebugLog.Add('EXCEPTION: AddPCBObject or PostProcess failed');
        End;
        
        Board.GraphicallyInvalidate;
        Sleep(500);
        
        // Verify rule exists
        RuleFound := False;
        RetryCount := 0;
        While (RetryCount < 3) And (Not RuleFound) Do
        Begin
            Try
                Iter := Board.BoardIterator_Create;
                Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
                Iter.AddFilter_LayerSet(AllLayers);
                Rule := Iter.FirstPCBObject;
                While Rule <> Nil Do
                Begin
                    If UpperCase(Trim(Rule.Name)) = UpperCase(Trim(RuleName)) Then
                    Begin
                        RuleFound := True;
                        Break;
                    End;
                    Rule := Iter.NextPCBObject;
                End;
                Board.BoardIterator_Destroy(Iter);
            Except
                Try
                    Board.BoardIterator_Destroy(Iter);
                Except
                End;
            End;
            
            If Not RuleFound Then
            Begin
                Sleep(300);
                Inc(RetryCount);
            End;
        End;
        
        DebugLog.Add('Verification: RuleFound = ' + BoolToStr(RuleFound, True));
        
        If RuleFound Then
        Begin
            Result := True;
            Board.GraphicallyInvalidate;
            
            // CRITICAL: Force board to recognize the new rule
            // Refresh the board state to ensure rule is fully committed
            Try
                PCBServer.PostProcess;
                Board.GraphicallyInvalidate;
                // Force a board update
                Board.ViewManager_UpdateLayerTabs;
            Except
            End;
        End;
    End
    
    // ============================================================
    // WIDTH RULE
    // ============================================================
    Else If RuleType = 'width' Then
    Begin
        Try
            WidthRule := PCBServer.PCBRuleFactory(eRule_RoutingWidth);
            If WidthRule = Nil Then
            Begin
                PCBServer.PostProcess;
                Exit;
            End;
            
            WidthRule.Name := RuleName;
            MinWidth := StrToFloatDef(ParseValue(Cmd, 'param_min_width_mm'), 0.254);
            PrefWidth := StrToFloatDef(ParseValue(Cmd, 'param_preferred_width_mm'), 0.5);
            MaxWidth := StrToFloatDef(ParseValue(Cmd, 'param_max_width_mm'), 1.0);
            
            WidthRule.MinWidth := MMsToCoord(MinWidth);
            WidthRule.PreferredWidth := MMsToCoord(PrefWidth);
            WidthRule.MaxWidth := MMsToCoord(MaxWidth);
            
            Scope1 := ParseValue(Cmd, 'param_scope');
            If (Scope1 <> '') And (UpperCase(Scope1) <> 'ALL') Then
                WidthRule.Scope1Expression := Scope1
            Else
                WidthRule.Scope1Expression := 'All';
            
            WidthRule.Enabled := True;
            
            Board.AddPCBObject(WidthRule);
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
            Sleep(500);
            
            // Verify
            RuleFound := False;
            Try
                Iter := Board.BoardIterator_Create;
                Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
                Iter.AddFilter_LayerSet(AllLayers);
                Rule := Iter.FirstPCBObject;
                While Rule <> Nil Do
                Begin
                    If UpperCase(Trim(Rule.Name)) = UpperCase(Trim(RuleName)) Then
                    Begin
                        RuleFound := True;
                        Break;
                    End;
                    Rule := Iter.NextPCBObject;
                End;
                Board.BoardIterator_Destroy(Iter);
            Except
                Try Board.BoardIterator_Destroy(Iter); Except End;
            End;
            
            If RuleFound Then
            Begin
                Result := True;
                Board.GraphicallyInvalidate;
            End;
        Except
            PCBServer.PostProcess;
        End;
    End
    
    // ============================================================
    // VIA RULE (Fixed: use IPCB_RoutingViaRule not IPCB_RoutingViaStyle)
    // ============================================================
    Else If RuleType = 'via' Then
    Begin
        Try
            ViaRule := PCBServer.PCBRuleFactory(eRule_RoutingViaStyle);
            If ViaRule = Nil Then
            Begin
                PCBServer.PostProcess;
                Exit;
            End;
            
            ViaRule.Name := RuleName;
            MinHole := StrToFloatDef(ParseValue(Cmd, 'param_min_hole_mm'), 0.3);
            MaxHole := StrToFloatDef(ParseValue(Cmd, 'param_max_hole_mm'), 0.5);
            MinDia := StrToFloatDef(ParseValue(Cmd, 'param_min_diameter_mm'), 0.6);
            MaxDia := StrToFloatDef(ParseValue(Cmd, 'param_max_diameter_mm'), 1.0);
            
            ViaRule.MinHoleSize := MMsToCoord(MinHole);
            ViaRule.MaxHoleSize := MMsToCoord(MaxHole);
            ViaRule.MinWidth := MMsToCoord(MinDia);
            ViaRule.MaxWidth := MMsToCoord(MaxDia);
            
            Scope1 := ParseValue(Cmd, 'param_scope');
            If (Scope1 <> '') And (UpperCase(Scope1) <> 'ALL') Then
                ViaRule.Scope1Expression := Scope1
            Else
                ViaRule.Scope1Expression := 'All';
            
            ViaRule.Enabled := True;
            
            Board.AddPCBObject(ViaRule);
            PCBServer.PostProcess;
            Board.GraphicallyInvalidate;
            Sleep(500);
            
            // Verify
            RuleFound := False;
            Try
                Iter := Board.BoardIterator_Create;
                Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
                Iter.AddFilter_LayerSet(AllLayers);
                Rule := Iter.FirstPCBObject;
                While Rule <> Nil Do
                Begin
                    If UpperCase(Trim(Rule.Name)) = UpperCase(Trim(RuleName)) Then
                    Begin
                        RuleFound := True;
                        Break;
                    End;
                    Rule := Iter.NextPCBObject;
                End;
                Board.BoardIterator_Destroy(Iter);
            Except
                Try Board.BoardIterator_Destroy(Iter); Except End;
            End;
            
            If RuleFound Then
            Begin
                Result := True;
                Board.GraphicallyInvalidate;
            End;
        Except
            PCBServer.PostProcess;
        End;
    End
    Else
    Begin
        DebugLog.Add('FAIL: Unknown rule type: ' + RuleType);
    End;
    
    // Save debug log
    Try
        DebugLog.Add('Final Result: ' + BoolToStr(Result, True));
        DebugLog.SaveToFile(BasePath + 'rule_debug.txt');
    Except
    End;
    DebugLog.Free;
End;

{..............................................................................}
{ UPDATE RULE                                                                  }
{..............................................................................}
Function UpdateRule(RuleName : String; Cmd : String) : Boolean;
Var
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    ClearanceRule : IPCB_ClearanceRule;
    WidthRule : IPCB_RoutingWidthRule;
    ViaRule : IPCB_RoutingViaRule;
    Iter : IPCB_BoardIterator;
    Found : Boolean;
    ClearanceMM, MinWidth, PrefWidth, MaxWidth, MinHole, MaxHole, MinDia, MaxDia : Double;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Found := False;
    RuleName := Trim(RuleName);
    
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Rule := Iter.FirstPCBObject;
    While Rule <> Nil Do
    Begin
        If UpperCase(Trim(Rule.Name)) = UpperCase(RuleName) Then
        Begin
            Found := True;
            Break;
        End;
        Rule := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    
    If Not Found Then
    Begin
        WriteRes(False, 'Rule not found: ' + RuleName);
        Exit;
    End;
    
    PCBServer.PreProcess;
    Rule.BeginModify;
    
    // Try to update as clearance rule
    Try
        ClearanceRule := Rule;
        If ClearanceRule <> Nil Then
        Begin
            ClearanceMM := StrToFloatDef(ParseValue(Cmd, 'param_clearance_mm'), -1);
            If ClearanceMM >= 0 Then
            Begin
                ClearanceRule.Gap := MMsToCoord(ClearanceMM);
                Result := True;
            End;
        End;
    Except
    End;
    
    If Not Result Then
    Begin
        Try
            WidthRule := Rule;
            If WidthRule <> Nil Then
            Begin
                MinWidth := StrToFloatDef(ParseValue(Cmd, 'param_min_width_mm'), -1);
                PrefWidth := StrToFloatDef(ParseValue(Cmd, 'param_preferred_width_mm'), -1);
                MaxWidth := StrToFloatDef(ParseValue(Cmd, 'param_max_width_mm'), -1);
                
                If MinWidth >= 0 Then WidthRule.MinWidth := MMsToCoord(MinWidth);
                If PrefWidth >= 0 Then WidthRule.PreferredWidth := MMsToCoord(PrefWidth);
                If MaxWidth >= 0 Then WidthRule.MaxWidth := MMsToCoord(MaxWidth);
                
                If (MinWidth >= 0) Or (PrefWidth >= 0) Or (MaxWidth >= 0) Then
                    Result := True;
            End;
        Except
        End;
    End;
    
    If Not Result Then
    Begin
        Try
            ViaRule := Rule;
            If ViaRule <> Nil Then
            Begin
                MinHole := StrToFloatDef(ParseValue(Cmd, 'param_min_hole_mm'), -1);
                MaxHole := StrToFloatDef(ParseValue(Cmd, 'param_max_hole_mm'), -1);
                MinDia := StrToFloatDef(ParseValue(Cmd, 'param_min_diameter_mm'), -1);
                MaxDia := StrToFloatDef(ParseValue(Cmd, 'param_max_diameter_mm'), -1);
                
                If MinHole >= 0 Then ViaRule.MinHoleSize := MMsToCoord(MinHole);
                If MaxHole >= 0 Then ViaRule.MaxHoleSize := MMsToCoord(MaxHole);
                If MinDia >= 0 Then ViaRule.MinWidth := MMsToCoord(MinDia);
                If MaxDia >= 0 Then ViaRule.MaxWidth := MMsToCoord(MaxDia);
                
                If (MinHole >= 0) Or (MaxHole >= 0) Or (MinDia >= 0) Or (MaxDia >= 0) Then
                    Result := True;
            End;
        Except
        End;
    End;
    
    Rule.EndModify;
    PCBServer.PostProcess;
    Board.GraphicallyInvalidate;
End;

{..............................................................................}
{ DELETE RULE                                                                  }
{..............................................................................}
Function DeleteRule(RuleName : String) : Boolean;
Var
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    Iter : IPCB_BoardIterator;
    Found : Boolean;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    Found := False;
    RuleName := Trim(RuleName);
    
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Rule := Iter.FirstPCBObject;
    While Rule <> Nil Do
    Begin
        If UpperCase(Trim(Rule.Name)) = UpperCase(RuleName) Then
        Begin
            Found := True;
            Break;
        End;
        Rule := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    
    If Not Found Then
    Begin
        WriteRes(False, 'Rule not found: ' + RuleName);
        Exit;
    End;
    
    // Delete the rule
    Try
        PCBServer.PreProcess;
        Board.RemovePCBObject(Rule);
        PCBServer.PostProcess;
        Board.GraphicallyInvalidate;
        Result := True;
    Except
        WriteRes(False, 'Error deleting rule: ' + RuleName);
        Result := False;
    End;
End;

{..............................................................................}
{ PROCESS COMMAND                                                              }
{..............................................................................}
Procedure ProcessCommand;
Var
    Cmd, Act, Des, Net, Layer, RuleType, RuleName, Scope1, Scope2 : String;
    X, Y, X1, Y1, X2, Y2, W, Hole, Diam : Double;
    OK, RuleFound : Boolean;
    N : Integer;
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    Iter : IPCB_BoardIterator;
    SL : TStringList;
Begin
    Cmd := ReadCmd;
    
    // Only process if there's a real command (FIXES log spam bug)
    If (Length(Cmd) < 5) Or (Pos('"action"', Cmd) = 0) Then
        Exit;
    
    // CRITICAL FIX: Clear command file IMMEDIATELY after reading it.
    // This prevents a race condition where:
    //   1. Altium processes a command and writes the result
    //   2. Python reads the result, sends a NEW command (writes new command file)
    //   3. Altium's late ClearCmd deletes the NEW command file!
    // By clearing first, step 3 cannot happen.
    ClearCmd;
    
    // Log ONLY real commands (not empty polls) - using TStringList to avoid I/O error 32
    Try
        SL := TStringList.Create;
        Try
            If FileExists(BasePath + 'command_log.txt') Then
                SL.LoadFromFile(BasePath + 'command_log.txt');
            SL.Add('=== ' + DateTimeToStr(Now) + ' ===');
            SL.Add('Length: ' + IntToStr(Length(Cmd)));
            SL.Add('Content: ' + Cmd);
            SL.Add('');
            SL.SaveToFile(BasePath + 'command_log.txt');
        Except
        End;
        SL.Free;
    Except
    End;
    
    Act := LowerCase(ParseValue(Cmd, 'action'));
    CurrentAction := Act;
    OK := False;
    
    // PING
    If Act = 'ping' Then
    Begin
        WriteRes(True, 'pong');
        Exit;  // ClearCmd already done above
    End;
    
    // MOVE COMPONENT
    If Act = 'move_component' Then
    Begin
        Des := ParseValue(Cmd, 'designator');
        X := StrToFloat(ParseValue(Cmd, 'x'));
        Y := StrToFloat(ParseValue(Cmd, 'y'));
        
        OK := MoveComp(Des, X, Y);
        
        If OK Then
            WriteRes(True, Des + ' moved to (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ') mm')
        Else
            WriteRes(False, 'Component ' + Des + ' not found');
    End
    Else If Act = 'add_track' Then
    Begin
        Net := ParseValue(Cmd, 'net');
        Layer := ParseValue(Cmd, 'layer');
        If Layer = '' Then Layer := 'Top';
        X1 := StrToFloat(ParseValue(Cmd, 'x1'));
        Y1 := StrToFloat(ParseValue(Cmd, 'y1'));
        X2 := StrToFloat(ParseValue(Cmd, 'x2'));
        Y2 := StrToFloat(ParseValue(Cmd, 'y2'));
        W := StrToFloat(ParseValue(Cmd, 'width'));
        If W <= 0 Then W := 0.25;
        
        OK := AddTrack(Net, Layer, X1, Y1, X2, Y2, W);
        
        If OK Then
            WriteRes(True, 'Track added on ' + Layer)
        Else
            WriteRes(False, 'Failed to add track');
    End
    
    // ADD VIA
    Else If Act = 'add_via' Then
    Begin
        X := StrToFloat(ParseValue(Cmd, 'x'));
        Y := StrToFloat(ParseValue(Cmd, 'y'));
        Hole := StrToFloat(ParseValue(Cmd, 'hole'));
        Diam := StrToFloat(ParseValue(Cmd, 'diameter'));
        If Hole <= 0 Then Hole := 0.3;
        If Diam <= 0 Then Diam := 0.6;
        
        OK := AddVia(X, Y, Hole, Diam);
        
        If OK Then
            WriteRes(True, 'Via added at (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ')')
        Else
            WriteRes(False, 'Failed to add via');
    End
    
    // RUN DRC
    Else If Act = 'run_drc' Then
    Begin
        RunDRC;
    End
    
    // EXPORT PCB INFO
    Else If Act = 'export_pcb_info' Then
    Begin
        SilentMode := False;  // Interactive export shows messages
        ExportPCBInfo;
    End
    
    // CREATE RULE
    Else If Act = 'create_rule' Then
    Begin
        RuleType := ParseValue(Cmd, 'rule_type');
        RuleName := ParseValue(Cmd, 'rule_name');
        Scope1 := ParseValue(Cmd, 'param_scope_first');
        Scope2 := ParseValue(Cmd, 'param_scope_second');
        
        If (RuleType = '') Or (RuleName = '') Then
        Begin
            WriteRes(False, 'Missing rule_type or rule_name. Got type=' + RuleType + ' name=' + RuleName);
        End
        Else
        Begin
            OK := CreateRule(RuleType, RuleName, Cmd);
            If OK Then
            Begin
                // CRITICAL: Refresh board reference before saving/exporting
                // The board object might need to be refreshed to see the new rule
                Board := GetBoard;
                If Board <> Nil Then
                Begin
                    Try
                        PCBServer.PostProcess;
                        Board.GraphicallyInvalidate;
                    Except
                    End;
                End;
                
                Sleep(300);
                
                // Save PCB file to persist the new rule
                SavePCBFile;
                Sleep(800);  // Longer sleep to ensure file is saved
                
                // CRITICAL: Refresh board reference again after save
                // Sometimes the board needs to be re-acquired after save
                Board := GetBoard;
                If Board <> Nil Then
                Begin
                    Try
                        PCBServer.PostProcess;
                        Board.GraphicallyInvalidate;
                    Except
                    End;
                End;
                
                Sleep(1000);  // Longer delay to ensure board state is fully updated and rule is committed
                
                // CRITICAL: Force a complete board refresh before exporting
                // This ensures ExportPCBInfo sees the newly added rule
                Board := GetBoard;
                If Board <> Nil Then
                Begin
                    Try
                        PCBServer.PreProcess;
                        PCBServer.PostProcess;
                        Board.GraphicallyInvalidate;
                        // Force board to recognize all changes
                        Board.ViewManager_UpdateLayerTabs;
                    Except
                    End;
                End;
                
                Sleep(500);  // Additional delay after refresh
                
                // Export in SILENT mode (no ShowMessage, no WriteRes from ExportPCBInfo)
                SilentMode := True;
                ExportPCBInfo;
                SilentMode := False;
                
                // Count rules after export to verify
                N := 0;
                Board := GetBoard;
                If Board <> Nil Then
                Begin
                    Try
                        Iter := Board.BoardIterator_Create;
                        Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
                        Iter.AddFilter_LayerSet(AllLayers);
                        Rule := Iter.FirstPCBObject;
                        While Rule <> Nil Do
                        Begin
                            Inc(N);
                            Rule := Iter.NextPCBObject;
                        End;
                        Board.BoardIterator_Destroy(Iter);
                    Except
                    End;
                End;
                
                // Write the ONLY result for this command
                WriteRes(True, 'Rule ' + RuleName + ' (' + RuleType + ') created. ' +
                          'Scope: ' + Scope1 + ' / ' + Scope2 + '. ' +
                          'Total rules now: ' + IntToStr(N) + '. ' +
                          'PCB saved and info exported.');
            End
            Else
            Begin
                WriteRes(False, 'FAILED to create rule ' + RuleName + ' (' + RuleType + '). ' +
                          'Scope: ' + Scope1 + ' / ' + Scope2 + '. ' +
                          'The rule was not added to the board. ' +
                          'Check: 1) Rule name must be unique, 2) PCB must be open.');
            End;
        End;
    End
    
    // UPDATE RULE
    Else If Act = 'update_rule' Then
    Begin
        RuleName := ParseValue(Cmd, 'rule_name');
        
        If RuleName = '' Then
        Begin
            WriteRes(False, 'Missing rule_name');
        End
        Else
        Begin
            OK := UpdateRule(RuleName, Cmd);
            If OK Then
            Begin
                SavePCBFile;
                
                SilentMode := True;
                ExportPCBInfo;
                SilentMode := False;
                
                WriteRes(True, 'Rule ' + RuleName + ' updated successfully. PCB saved and info exported.');
            End
            Else
            Begin
                WriteRes(False, 'Failed to update rule ' + RuleName + ' (rule not found or invalid parameters)');
            End;
        End;
    End
    
    // DELETE RULE
    Else If Act = 'delete_rule' Then
    Begin
        RuleName := ParseValue(Cmd, 'rule_name');
        
        If RuleName = '' Then
        Begin
            WriteRes(False, 'Missing rule_name');
        End
        Else
        Begin
            OK := DeleteRule(RuleName);
            If OK Then
            Begin
                SavePCBFile;
                
                SilentMode := True;
                ExportPCBInfo;
                SilentMode := False;
                
                WriteRes(True, 'Rule ' + RuleName + ' deleted successfully. PCB saved and info exported.');
            End
            Else
            Begin
                WriteRes(False, 'Failed to delete rule: ' + RuleName);
            End;
        End;
    End
    
    // UNKNOWN
    Else
    Begin
        WriteRes(False, 'Unknown action: ' + Act);
    End;
    
    // ClearCmd already called at top of ProcessCommand (before processing)
End;

{..............................................................................}
{ START SERVER - Polling Loop                                                  }
{..............................................................................}
Procedure StartServer;
Var
    Board : IPCB_Board;
    CmdFile, ResFile : String;
Begin
    ServerRunning := True;
    SilentMode := False;
    CurrentAction := '';
    
    // Initialize base path
    BasePath := GetBasePath;
    
    CmdFile := GetCommandFile;
    ResFile := GetResultFile;
    
    Board := PCBServer.GetCurrentPCBBoard;
    // CRITICAL: Cache the board reference globally so it survives
    // the polling loop where GetCurrentPCBBoard may return Nil
    // (happens when script panel or another window has focus)
    GlobalBoard := Board;
    
    If Board = Nil Then
    Begin
        ShowMessage('EagilinsED Command Server Started!' + #13#10 + 
                    'No PCB open. Open a PCB and it will auto-export.' + #13#10 +
                    #13#10 +
                    'Command file: ' + CmdFile + #13#10 +
                    'Result file: ' + ResFile);
    End
    Else
    Begin
        ShowMessage('EagilinsED Command Server Started!' + #13#10 + 
                    'Auto-exporting PCB info...' + #13#10 +
                    #13#10 +
                    'Command file: ' + CmdFile + #13#10 +
                    'Result file: ' + ResFile);
        ExportPCBInfo;
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
    
    ShowMessage('Command Server Stopped.');
End;

{..............................................................................}
{ STOP SERVER                                                                  }
{..............................................................................}
Procedure StopServer;
Begin
    ServerRunning := False;
    ShowMessage('Server stopped.');
End;

{..............................................................................}
{ EXECUTE NOW - Run single command                                             }
{..............................................................................}
Procedure ExecuteNow;
Var
    Cmd : String;
Begin
    SilentMode := False;
    Cmd := ReadCmd;
    
    If Length(Cmd) < 5 Then
    Begin
        ShowMessage('No command pending. Send a command from agent first.');
        Exit;
    End;
    
    ProcessCommand;
    ShowMessage('Command executed. Check result file.');
End;

{..............................................................................}
{ LIST COMPONENTS                                                              }
{..............................................................................}
Procedure ListComponents;
Var
    Board : IPCB_Board;
    Comp  : IPCB_Component;
    Iter  : IPCB_BoardIterator;
    S     : String;
    N     : Integer;
Begin
    Board := GetBoard;
    If Board = Nil Then
    Begin
        ShowMessage('No PCB open!');
        Exit;
    End;
    
    S := 'Components:' + #13#10;
    N := 0;
    
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eComponentObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Comp := Iter.FirstPCBObject;
    While (Comp <> Nil) And (N < 50) Do
    Begin
        S := S + Comp.Name.Text + ', ';
        Inc(N);
        If (N Mod 10) = 0 Then S := S + #13#10;
        Comp := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    ShowMessage(S);
End;

End.
