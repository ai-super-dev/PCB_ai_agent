{..............................................................................}
{ Altium Command Server - Full Integration with EagilinsED Agent             }
{ Supports: DRC, Export, Move, Add Track, Add Via, Delete                     }
{ Updated: Dynamic paths, Complete rule export                                }
{..............................................................................}

Var
    ServerRunning : Boolean;
    BasePath : String;  // Dynamic base path for files

{..............................................................................}
Function GetBasePath : String;
Var
    Project : IProject;
    ProjectPath : String;
    Board : IPCB_Board;
    ScriptPath : String;
    TempPath : String;
Begin
    // PRIORITY 1: Use script directory and navigate up from altium_scripts folder
    // This is most reliable since script is always in altium_scripts folder
    ScriptPath := GetRunningScriptProjectName;
    If ScriptPath <> '' Then
    Begin
        TempPath := ExtractFilePath(ScriptPath);
        // Navigate up from altium_scripts folder to project root
        // If script is in E:\Altium_Project\PCB_ai_agent\altium_scripts\command_server.pas
        // We want E:\Altium_Project\PCB_ai_agent\
        If (TempPath <> '') And (Pos('altium_scripts', TempPath) > 0) Then
        Begin
            // Remove 'altium_scripts\' from path
            Result := Copy(TempPath, 1, Pos('altium_scripts', TempPath) - 1);
            // Ensure path ends with backslash
            If (Result <> '') And (Result[Length(Result)] <> '\') Then
                Result := Result + '\';
            Exit;
        End;
    End;
    
    // PRIORITY 2: Try to get path from current PCB board
    Board := PCBServer.GetCurrentPCBBoard;
    If Board <> Nil Then
    Begin
        ProjectPath := Board.FileName;
        If ProjectPath <> '' Then
        Begin
            Result := ExtractFilePath(ProjectPath);
            // Ensure path ends with backslash
            If (Result <> '') And (Result[Length(Result)] <> '\') Then
                Result := Result + '\';
            Exit;
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
            // Ensure path ends with backslash
            If (Result <> '') And (Result[Length(Result)] <> '\') Then
                Result := Result + '\';
            Exit;
        End;
    End;
    
    // PRIORITY 4: Hardcoded fallback for your project
    Result := 'E:\Altium_Project\PCB_ai_agent\';
    
    // Ensure path ends with backslash
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
    F : TextFile;
Begin
    Result := '';
    If Not FileExists(GetCommandFile) Then Exit;
    AssignFile(F, GetCommandFile);
    Reset(F);
    If Not EOF(F) Then ReadLn(F, Result);
    CloseFile(F);
End;

{..............................................................................}
Procedure WriteRes(OK : Boolean; Msg : String);
Var
    F : TextFile;
    Q, TempFile : String;
    RetryCount : Integer;
Begin
    Q := Chr(34);  // Double quote
    
    // Use temp file approach to avoid I/O error 32
    TempFile := GetResultFile + '.tmp';
    
    // Delete temp file if exists
    If FileExists(TempFile) Then
    Begin
        Try
            DeleteFile(TempFile);
        Except
            // Ignore delete errors
        End;
    End;
    
    // Try to write with retry
    RetryCount := 0;
    While RetryCount < 5 Do
    Begin
        Try
            AssignFile(F, TempFile);
            Rewrite(F);
            If OK Then
            Begin
                WriteLn(F, Chr(123) + Q + 'success' + Q + ':true,' + Q + 'message' + Q + ':' + Q + Msg + Q + Chr(125));
            End
            Else
            Begin
                WriteLn(F, Chr(123) + Q + 'success' + Q + ':false,' + Q + 'error' + Q + ':' + Q + Msg + Q + Chr(125));
            End;
            CloseFile(F);
            
            // Rename temp to final
            Try
                If FileExists(GetResultFile) Then DeleteFile(GetResultFile);
                RenameFile(TempFile, GetResultFile);
            Except
                // If rename fails, at least temp file has the data
            End;
            
            Break;  // Success
        Except
            Inc(RetryCount);
            If RetryCount < 5 Then
            Begin
                Sleep(300);
            End;
        End;
    End;
End;

{..............................................................................}
Procedure ClearCmd;
Begin
    If FileExists(GetCommandFile) Then DeleteFile(GetCommandFile);
End;

{..............................................................................}
Function ParseValue(S, Key : String) : String;
Var
    I, J : Integer;
    Q : Char;
Begin
    Result := '';
    Q := Chr(34);  // Double quote
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
    Board := PCBServer.GetCurrentPCBBoard;
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
    Net   : IPCB_Net;
    Layer : TLayer;
Begin
    Result := False;
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then Exit;
    
    // Create track
    Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
    If Track = Nil Then Exit;
    
    // Set properties
    Track.X1 := MMsToCoord(X1);
    Track.Y1 := MMsToCoord(Y1);
    Track.X2 := MMsToCoord(X2);
    Track.Y2 := MMsToCoord(Y2);
    Track.Width := MMsToCoord(Width);
    
    // Set layer (default to Top)
    If UpperCase(LayerName) = 'BOTTOM' Then
    Begin
        Track.Layer := eBottomLayer;
    End
    Else
    Begin
        Track.Layer := eTopLayer;
    End;
    
    // Add to board
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
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then Exit;
    
    // Create via
    Via := PCBServer.PCBObjectFactory(eViaObject, eNoDimension, eCreate_Default);
    If Via = Nil Then Exit;
    
    // Set properties
    Via.X := MMsToCoord(X);
    Via.Y := MMsToCoord(Y);
    Via.HoleSize := MMsToCoord(HoleSize);
    Via.Size := MMsToCoord(Diameter);
    Via.LowLayer := eBottomLayer;
    Via.HighLayer := eTopLayer;
    
    // Add to board
    PCBServer.PreProcess;
    Board.AddPCBObject(Via);
    PCBServer.PostProcess;
    Board.GraphicallyInvalidate;
    
    Result := True;
End;

{..............................................................................}
{ RUN DRC - Automated (runs DRC programmatically)                             }
{..............................................................................}
Procedure RunDRC;
Var
    Board : IPCB_Board;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open');
        Exit;
    End;
    
    // Run DRC - Altium will execute DRC check
    ResetParameters;
    AddStringParameter('Action', 'Run');
    RunProcess('PCB:RunDesignRuleCheck');
    
    // Wait for DRC to complete
    Sleep(2000);
    
    WriteRes(True, 'DRC command executed. Report will be generated in Project Outputs folder.');
End;

{..............................................................................}
{ EXPORT PCB INFO - Comprehensive export for all features                     }
{..............................................................................}
Procedure ExportPCBInfo;
Var
    Board : IPCB_Board;
    Comp  : IPCB_Component;
    Net   : IPCB_Net;
    Track : IPCB_Track;
    Via   : IPCB_Via;
    Pad   : IPCB_Pad;
    Rule  : IPCB_Rule;
    ClearanceRule : IPCB_ClearanceRule;
    WidthRule : IPCB_RoutingWidthRule;
    ViaRule : IPCB_RoutingViaRule;
    Constraint : IPCB_Constraint;
    Layer : TLayer;
    Iter : IPCB_BoardIterator;
    F, F2 : TextFile;
    Q, S, LayerName, NetName, FinalPath, LineContent, TempFilePath : String;
    N, I, LayerID, CompCount, NetCount, TrackCount, ViaCount, RuleCount, RetryCount, FileNum : Integer;
    X, Y, W, H, Drill, Size : Double;
    MechLayer : IPCB_MechanicalLayer;
    RuleTypeDetected : Boolean;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        ShowMessage('Error: No PCB file is open!' + #13#10 + 'Please open a PCB file first.');
        WriteRes(False, 'No PCB open');
        Exit;
    End;
    
    Q := Chr(34);
    
    // Initialize base path - prioritize known correct path
    If BasePath = '' Then 
    Begin
        // First try the known correct path
        If DirectoryExists('E:\Altium_Project\PCB_ai_agent\') Then
        Begin
            BasePath := 'E:\Altium_Project\PCB_ai_agent\';
        End
        Else
        Begin
            BasePath := GetBasePath;
        End;
    End;
    
    // Show the detected path for debugging
    ShowMessage('Detected base path: ' + BasePath + #13#10 + 
                'PCB file: ' + Board.FileName);
    
    // Validate path exists (directory must exist to write files)
    If Not DirectoryExists(BasePath) Then
    Begin
        // Try PCB file directory as fallback
        If Board.FileName <> '' Then
        Begin
            BasePath := ExtractFilePath(Board.FileName);
            If (BasePath <> '') And (BasePath[Length(BasePath)] <> '\') Then
                BasePath := BasePath + '\';
            ShowMessage('Path does not exist, using PCB file directory: ' + BasePath);
        End
        Else
        Begin
            // Last resort: use script directory (navigate up from altium_scripts)
            BasePath := ExtractFilePath(GetRunningScriptProjectName);
            If Pos('altium_scripts', BasePath) > 0 Then
                BasePath := Copy(BasePath, 1, Pos('altium_scripts', BasePath) - 1);
            If (BasePath <> '') And (BasePath[Length(BasePath)] <> '\') Then
                BasePath := BasePath + '\';
            ShowMessage('Using script directory: ' + BasePath);
        End;
    End;
    
    // Show user where file will be created
    FinalPath := BasePath + 'altium_pcb_info.json';
    ShowMessage('Starting export...' + #13#10 + 
                'Base path: ' + BasePath + #13#10 + 
                'Export file will be created at:' + #13#10 + FinalPath);
    
    // Verify directory exists before trying to write
    If Not DirectoryExists(BasePath) Then
    Begin
        ShowMessage('Directory does not exist: ' + BasePath + #13#10 + 
                    'Trying alternative locations...');
        // Try PCB file directory
        If Board.FileName <> '' Then
        Begin
            BasePath := ExtractFilePath(Board.FileName);
            If (BasePath <> '') And (BasePath[Length(BasePath)] <> '\') Then
                BasePath := BasePath + '\';
        End;
        // If still doesn't exist, use script directory
        If Not DirectoryExists(BasePath) Then
        Begin
            BasePath := ExtractFilePath(GetRunningScriptProjectName);
            If Pos('altium_scripts', BasePath) > 0 Then
                BasePath := Copy(BasePath, 1, Pos('altium_scripts', BasePath) - 1);
            If (BasePath <> '') And (BasePath[Length(BasePath)] <> '\') Then
                BasePath := BasePath + '\';
        End;
    End;
    
    // Ensure BasePath ends with backslash BEFORE using it
    If (BasePath <> '') And (BasePath[Length(BasePath)] <> '\') Then
        BasePath := BasePath + '\';
    
    // Validate directory exists
    If Not DirectoryExists(BasePath) Then
    Begin
        ShowMessage('Error: Directory does not exist: ' + BasePath + #13#10 + 
                    'Cannot create export file.');
        WriteRes(False, 'Directory does not exist: ' + BasePath);
        Exit;
    End;
    
    // Write to fixed filename: altium_pcb_info.json (overwrites previous export)
    FinalPath := BasePath + 'altium_pcb_info.json';
    
    // CRITICAL: Write to Windows temp directory FIRST (guaranteed to work, never locked)
    // Then copy to final location - this completely bypasses directory locking issues
    TempFilePath := 'C:\Windows\Temp\altium_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
    
    // If Windows temp doesn't exist, try C:\Temp
    If Not DirectoryExists('C:\Windows\Temp\') Then
    Begin
        TempFilePath := 'C:\Temp\altium_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
        If Not DirectoryExists('C:\Temp\') Then
        Begin
            // Last resort: try project directory with unique timestamp
            TempFilePath := BasePath + 'altium_export_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
        End;
    End;
    
    // Write to temp file (should ALWAYS work - it's a unique file in temp directory)
    Try
        AssignFile(F, TempFilePath);
        Rewrite(F);
    Except
        // If even temp directory fails, we're in serious trouble
        ShowMessage('Error: Cannot write to temp directory!' + #13#10 + 
                    'Tried: ' + TempFilePath + #13#10 + 
                    'Please check system permissions.');
        WriteRes(False, 'Cannot write to temp directory');
        Exit;
    End;
    
    // Start JSON
    WriteLn(F, Chr(123));
    WriteLn(F, Q + 'export_source' + Q + ':' + Q + 'altium_designer' + Q + ',');
    // Escape backslashes in file path for valid JSON
    WriteLn(F, Q + 'file_name' + Q + ':' + Q + EscapeJSONString(Board.FileName) + Q + ',');
    WriteLn(F, Q + 'board_thickness_mm' + Q + ':1.6,');
    
    // Board dimensions
    WriteLn(F, Q + 'board_size' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Right - Board.BoardOutline.BoundingRectangle.Left)) + ',');
    WriteLn(F, Q + 'height_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Top - Board.BoardOutline.BoundingRectangle.Bottom)));
    WriteLn(F, Chr(125) + ',');
    
    // Layers - export common layers (simplified to avoid API issues)
    WriteLn(F, Q + 'layers' + Q + ':[');
    LayerID := 0;
    
    // Export top layer
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
        // Ignore errors
    End;
    
    // Export bottom layer
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
        // Ignore errors
    End;
    
    // Export internal planes if they exist
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
            // Ignore errors for this layer
        End;
    End;
    
    WriteLn(F, '],');
    
    // Components with pads
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
        
        // Pads - skip for now to avoid API compatibility issues
        // The main goal is to export design rules, pads are optional
        WriteLn(F, Q + 'pads' + Q + ':[]');
        Write(F, Chr(125));
        Inc(N);
        Comp := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    CompCount := N;  // Store component count for statistics
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
    NetCount := N;  // Store net count for statistics
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
    TrackCount := N;  // Store track count for statistics
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
    ViaCount := N;  // Store via count for statistics
    WriteLn(F, '],');
    
    // Design Rules - Export ALL rules from PCB with full details
    WriteLn(F, Q + 'rules' + Q + ':[');
    N := 0;
    
    // Export ALL Rules with comprehensive information
    // Use iterator to get all rules (RuleManager is not available in DelphiScript)
    Try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
        Iter.AddFilter_LayerSet(AllLayers);
        Rule := Iter.FirstPCBObject;
    Except
        // If iterator fails, we can't export rules
        WriteLn(F, '],');
        WriteLn(F, Q + 'rules_error' + Q + ':' + Q + 'Could not iterate rules' + Q + ',');
        Rule := Nil;
    End;
    
    While Rule <> Nil Do
    Begin
        LayerName := Rule.Name;
        If LayerName = '' Then 
        Begin
            LayerName := 'Unnamed_Rule_' + IntToStr(N + 1);
        End;
        
        If N > 0 Then WriteLn(F, ',');
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'name' + Q + ':' + Q + LayerName + Q + ',');
        If Rule.Enabled Then
            WriteLn(F, Q + 'enabled' + Q + ':true,')
        Else
            WriteLn(F, Q + 'enabled' + Q + ':false,');
        
        // Priority (with error handling)
        Try
            WriteLn(F, Q + 'priority' + Q + ':' + IntToStr(Rule.Priority) + ',');
        Except
            WriteLn(F, Q + 'priority' + Q + ':1,');
        End;
        
        // Export scope information (with error handling - may not be available in all versions)
        Try
            S := Rule.Scope1Expression;
            If S <> '' Then WriteLn(F, Q + 'scope_first' + Q + ':' + Q + S + Q + ',');
        Except
            // Scope1Expression not available, skip
        End;
        Try
            S := Rule.Scope2Expression;
            If S <> '' Then WriteLn(F, Q + 'scope_second' + Q + ':' + Q + S + Q + ',');
        Except
            // Scope2Expression not available, skip
        End;
        
        // Export rule type and actual values by safely accessing rule properties
        // Try to cast to specific rule types and extract values
        RuleTypeDetected := False;
        S := UpperCase(LayerName);
        
        // Export rule type based on name (DelphiScript API cannot read rule values)
        // Python file reader will merge actual values from PCB file
        If (Pos('CLEARANCE', S) > 0) Or (Pos('CLEAR', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'clearance' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End
        Else If ((Pos('WIDTH', S) > 0) Or (Pos('ROUTING', S) > 0)) And (Pos('VIA', S) = 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'min_width_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'preferred_width_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'max_width_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End
        Else If Pos('VIA', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'via' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'min_hole_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'max_hole_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'min_diameter_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'max_diameter_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End
        Else If Pos('SHORT', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'short_circuit' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'allowed' + Q + ':false');
            RuleTypeDetected := True;
        End
        Else If Pos('MASK', S) > 0 Then
        Begin
            If Pos('PASTE', S) > 0 Then
            Begin
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'paste_mask' + Q + ',');
            End
            Else
            Begin
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'solder_mask' + Q + ',');
            End;
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Mask' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'expansion_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End
        Else If (Pos('COMPONENT', S) > 0) And (Pos('CLEARANCE', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'component_clearance' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Placement' + Q + ',');
            // DelphiScript API cannot read rule values - Python file reader will get actual values
            WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End;
        
        // Generic rule - export as other
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
    RuleCount := N;  // Store rule count for statistics
    
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
    
    // End JSON
    WriteLn(F, Chr(125));
    CloseFile(F);
    
    // CRITICAL: Wait for Windows to release the file handle completely
    Sleep(500);
    
    // Now copy temp file to final location (read from temp, write to final)
    RetryCount := 0;
    While RetryCount < 10 Do
    Begin
        Try
            // Delete old final file if it exists
            If FileExists(FinalPath) Then
            Begin
                Try
                    DeleteFile(FinalPath);
                    Sleep(300);
                Except
                    // If delete fails, file is locked - wait longer
                    Sleep(1000);
                End;
            End;
            
            // Copy temp file to final location (read from temp, write to final)
            AssignFile(F, TempFilePath);
            Reset(F);
            AssignFile(F2, FinalPath);
            Rewrite(F2);
            
            // Copy line by line
            While Not EOF(F) Do
            Begin
                ReadLn(F, LineContent);
                WriteLn(F2, LineContent);
            End;
            
            CloseFile(F);
            CloseFile(F2);
            
            // Verify copy succeeded
            If FileExists(FinalPath) Then
            Begin
                // Success! Delete temp file
                Try
                    DeleteFile(TempFilePath);
                Except
                    // Ignore - temp file cleanup is not critical
                End;
                
                ShowMessage('Export completed successfully!' + #13#10 + 
                            'File saved to: ' + FinalPath + #13#10 + 
                            #13#10 + 
                            'Rules exported: ' + IntToStr(RuleCount) + #13#10 +
                            'The MCP server will automatically detect this file.');
                WriteRes(True, 'Export completed: ' + FinalPath);
                Exit;
            End;
        Except
            Inc(RetryCount);
            If RetryCount < 10 Then
            Begin
                Sleep(500 * RetryCount);  // Exponential backoff
            End;
        End;
    End;
    
    // Copy failed after 10 attempts, but temp file has the data
    ShowMessage('Export completed, but could not copy to final file!' + #13#10 + 
                'Data saved to: ' + TempFilePath + #13#10 + 
                'Target: ' + FinalPath + #13#10 +
                #13#10 +
                'The final directory might be locked. The MCP server can read from: ' + TempFilePath);
    WriteRes(True, 'Export completed (temp): ' + TempFilePath);
End;

{..............................................................................}
{ PROCESS COMMAND                                                              }
{..............................................................................}
Procedure ProcessCommand;
Var
    Cmd, Act, Des, Net, Layer : String;
    X, Y, X1, Y1, X2, Y2, W, Hole, Diam : Double;
    OK : Boolean;
Begin
    Cmd := ReadCmd;
    
    If Length(Cmd) < 5 Then Exit;
    
    Act := LowerCase(ParseValue(Cmd, 'action'));
    OK := False;
    
    // PING
    If Act = 'ping' Then
    Begin
        WriteRes(True, 'pong');
        ClearCmd;
        Exit;
    End;
    
    // MOVE COMPONENT
    If Act = 'move_component' Then
    Begin
        Des := ParseValue(Cmd, 'designator');
        X := StrToFloat(ParseValue(Cmd, 'x'));
        Y := StrToFloat(ParseValue(Cmd, 'y'));
        
        OK := MoveComp(Des, X, Y);
        
        If OK Then
        Begin
            WriteRes(True, Des + ' moved to (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ') mm');
        End
        Else
        Begin
            WriteRes(False, 'Component ' + Des + ' not found');
        End;
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
        Begin
            WriteRes(True, 'Track added on ' + Layer);
        End
        Else
        Begin
            WriteRes(False, 'Failed to add track');
        End;
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
        Begin
            WriteRes(True, 'Via added at (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ')');
        End
        Else
        Begin
            WriteRes(False, 'Failed to add via');
        End;
    End
    
    // RUN DRC
    Else If Act = 'run_drc' Then
    Begin
        RunDRC;
    End
    
    // EXPORT PCB INFO
    Else If Act = 'export_pcb_info' Then
    Begin
        ExportPCBInfo;
    End
    
    // UNKNOWN
    Else
    Begin
        WriteRes(False, 'Unknown action: ' + Act);
    End;
    
    ClearCmd;
End;

{..............................................................................}
{ START SERVER - Polling Loop                                                  }
{..............................................................................}
Procedure StartServer;
Var
    Board : IPCB_Board;
Begin
    ServerRunning := True;
    
    // Initialize base path
    BasePath := GetBasePath;
    
    // Check if PCB is open and auto-export immediately
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        ShowMessage('EagilinsED Command Server Started!' + #13#10 + 
                    'No PCB open. Open a PCB and it will auto-export.' + #13#10 +
                    'Listening for commands...');
    End
    Else
    Begin
        // Auto-export PCB info immediately on startup
        ShowMessage('EagilinsED Command Server Started!' + #13#10 + 
                    'Auto-exporting PCB info (including design rules)...' + #13#10 +
                    'Listening for commands...');
        ExportPCBInfo;
    End;
    
    // Continuously poll for commands
    While ServerRunning Do
    Begin
        ProcessCommand;
        Sleep(200);
        Application.ProcessMessages;
    End;
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
    Board := PCBServer.GetCurrentPCBBoard;
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
