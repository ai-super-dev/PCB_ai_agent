{..............................................................................}
{ Altium Command Server - Full Integration with EagilinsED Agent             }
{ Supports: DRC, Export, Move, Add Track, Add Via, Delete                     }
{..............................................................................}

Const
    COMMAND_FILE = 'D:\Work\workspace\Wayne\EagilinsED_PCB-Design-Agent\altium_command.json';
    RESULT_FILE  = 'D:\Work\workspace\Wayne\EagilinsED_PCB-Design-Agent\altium_result.json';
    PCB_INFO_FILE = 'D:\Work\workspace\Wayne\EagilinsED_PCB-Design-Agent\altium_pcb_info.json';

Var
    ServerRunning : Boolean;

{..............................................................................}
Function ReadCmd : String;
Var
    F : TextFile;
Begin
    Result := '';
    If Not FileExists(COMMAND_FILE) Then Exit;
    AssignFile(F, COMMAND_FILE);
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
    TempFile := RESULT_FILE + '.tmp';
    
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
                If FileExists(RESULT_FILE) Then DeleteFile(RESULT_FILE);
                RenameFile(TempFile, RESULT_FILE);
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
    If FileExists(COMMAND_FILE) Then DeleteFile(COMMAND_FILE);
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
    // Note: Some Altium versions may show a dialog, but most will run automatically
    ResetParameters;
    AddStringParameter('Action', 'Run');
    RunProcess('PCB:RunDesignRuleCheck');
    
    // Wait for DRC to complete and report to be generated
    // Large designs may take several seconds
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
    Layer : TLayer;
    Iter  : IPCB_BoardIterator;
    F     : TextFile;
    Q, S, LayerName, NetName : String;
    N, I, LayerID, RetryCount : Integer;
    X, Y, W, H, Drill, Size : Double;
    MechLayer : IPCB_MechanicalLayer;
Begin
    Board := PCBServer.GetCurrentPCBBoard;
    If Board = Nil Then
    Begin
        WriteRes(False, 'No PCB open');
        Exit;
    End;
    
    Q := Chr(34);
    
    // CRITICAL FIX: Write to a NEW file that Python never reads, then rename
    // This completely avoids file locking issues
    // Use timestamp-based filename that Python doesn't know about
    S := FormatDateTime('yyyymmddhhnnsszzz', Now);
    S := ExtractFilePath(PCB_INFO_FILE) + 'altium_export_' + S + '.json';
    
    // Write to the new file (this should never be locked)
    RetryCount := 0;
    While RetryCount < 5 Do
    Begin
        Try
            AssignFile(F, S);
            Rewrite(F);
            Break;  // SUCCESS - new file created!
        Except
            Inc(RetryCount);
            If RetryCount < 5 Then
            Begin
                Sleep(200);
                // Generate new unique name
                S := FormatDateTime('yyyymmddhhnnsszzz', Now);
                S := ExtractFilePath(PCB_INFO_FILE) + 'altium_export_' + S + '.json';
            End
            Else
            Begin
                WriteRes(False, 'Cannot create export file. Check disk space and permissions.');
                Exit;
            End;
        End;
    End;
    
    // Start JSON
    WriteLn(F, Chr(123));
    WriteLn(F, Q + 'export_source' + Q + ':' + Q + 'altium_designer' + Q + ',');
    WriteLn(F, Q + 'file_name' + Q + ':' + Q + Board.FileName + Q + ',');
    // Board thickness - use default 1.6mm (standard PCB thickness)
    // Note: Altium API doesn't provide direct OverallThickness property
    // You can manually set this in Altium: Design -> Layer Stack Manager
    WriteLn(F, Q + 'board_thickness_mm' + Q + ':1.6,');
    
    // Board dimensions
    WriteLn(F, Q + 'board_size' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'width_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Right - Board.BoardOutline.BoundingRectangle.Left)) + ',');
    WriteLn(F, Q + 'height_mm' + Q + ':' + FloatToStr(CoordToMMs(Board.BoardOutline.BoundingRectangle.Top - Board.BoardOutline.BoundingRectangle.Bottom)));
    WriteLn(F, Chr(125) + ',');
    
    // Layers
    WriteLn(F, Q + 'layers' + Q + ':[');
    For I := 0 To Board.LayerStack.LayerCount - 1 Do
    Begin
        Layer := Board.LayerStack.Layer(I);
        LayerName := Board.LayerName(Layer);
        If I > 0 Then WriteLn(F, ',');
        
        // Determine layer kind
        S := 'signal';
        If (Layer = eTopLayer) Or (Layer = eBottomLayer) Then 
        Begin
            S := 'signal';
        End
        Else If (Layer = eInternalPlane1) Or (Layer = eInternalPlane2) Or (Layer = eInternalPlane3) Or (Layer = eInternalPlane4) Then
        Begin
            If Pos('GND', UpperCase(LayerName)) > 0 Then 
            Begin
                S := 'ground';
            End
            Else If (Pos('VCC', UpperCase(LayerName)) > 0) Or (Pos('POWER', UpperCase(LayerName)) > 0) Then 
            Begin
                S := 'power';
            End;
        End;
        
        WriteLn(F, Chr(123) + Q + 'id' + Q + ':' + Q + 'L' + IntToStr(I+1) + Q);
        WriteLn(F, ',' + Q + 'name' + Q + ':' + Q + LayerName + Q);
        WriteLn(F, ',' + Q + 'kind' + Q + ':' + Q + S + Q);
        WriteLn(F, ',' + Q + 'index' + Q + ':' + IntToStr(I+1));
        Write(F, Chr(125));
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
        
        // Pads (iterate through component pads)
        WriteLn(F, Q + 'pads' + Q + ':[');
        I := 0;
        Pad := Comp.FirstPad;
        While Pad <> Nil Do
        Begin
            If I > 0 Then WriteLn(F, ',');
            NetName := '';
            If Pad.Net <> Nil Then NetName := Pad.Net.Name;
            
            WriteLn(F, Chr(123));
            WriteLn(F, Q + 'name' + Q + ':' + Q + Pad.Name + Q + ',');
            WriteLn(F, Q + 'net' + Q + ':' + Q + NetName + Q + ',');
            WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Pad.X)) + ',');
            WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Pad.Y)) + ',');
            WriteLn(F, Q + 'size_x_mm' + Q + ':' + FloatToStr(CoordToMMs(Pad.TopXSize)) + ',');
            WriteLn(F, Q + 'size_y_mm' + Q + ':' + FloatToStr(CoordToMMs(Pad.TopYSize)) + ',');
            WriteLn(F, Q + 'hole_size_mm' + Q + ':' + FloatToStr(CoordToMMs(Pad.HoleSize)) + ',');
            WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Pad.Layer) + Q);
            Write(F, Chr(125));
            Inc(I);
            Pad := Pad.NextPad;
        End;
        WriteLn(F, ']');
        Write(F, Chr(125));
        Inc(N);
        Comp := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
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
        WriteLn(F, Q + 'name' + Q + ':' + Q + Net.Name + Q + ',');
        WriteLn(F, Q + 'id' + Q + ':' + Q + IntToStr(Net.NetID) + Q);
        Write(F, Chr(125));
        Inc(N);
        Net := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
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
    WriteLn(F, '],');
    
    // Design Rules - Export actual rules from PCB
    WriteLn(F, Q + 'rules' + Q + ':[');
    N := 0;
    
    // Export Clearance Rules
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Rule := Iter.FirstPCBObject;
    While Rule <> Nil Do
    Begin
        LayerName := Rule.Name;
        If LayerName = '' Then LayerName := 'Unnamed Rule';
        
        // Check rule type and cast appropriately
        If Rule.RuleKind = eRule_Clearance Then
        Begin
            ClearanceRule := Rule;
            If N > 0 Then WriteLn(F, ',');
            WriteLn(F, Chr(123));
            WriteLn(F, Q + 'name' + Q + ':' + Q + LayerName + Q + ',');
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'clearance' + Q + ',');
            WriteLn(F, Q + 'clearance_mm' + Q + ':' + FloatToStr(CoordToMMs(ClearanceRule.Gap)));
            Write(F, Chr(125));
            Inc(N);
        End
        Else If Rule.RuleKind = eRule_RoutingWidth Then
        Begin
            WidthRule := Rule;
            If N > 0 Then WriteLn(F, ',');
            WriteLn(F, Chr(123));
            WriteLn(F, Q + 'name' + Q + ':' + Q + LayerName + Q + ',');
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
            WriteLn(F, Q + 'min_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MinWidth)) + ',');
            WriteLn(F, Q + 'preferred_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.PreferedWidth)) + ',');
            WriteLn(F, Q + 'max_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MaxWidth)));
            Write(F, Chr(125));
            Inc(N);
        End
        Else If Rule.RuleKind = eRule_RoutingVias Then
        Begin
            ViaRule := Rule;
            If N > 0 Then WriteLn(F, ',');
            WriteLn(F, Chr(123));
            WriteLn(F, Q + 'name' + Q + ':' + Q + LayerName + Q + ',');
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'via' + Q + ',');
            WriteLn(F, Q + 'min_hole_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MinHoleSize)) + ',');
            WriteLn(F, Q + 'min_diameter_mm' + Q + ':' + FloatToStr(CoordToMMs(ViaRule.MinDiameter)));
            Write(F, Chr(125));
            Inc(N);
        End;
        
        Rule := Iter.NextPCBObject;
    End;
    Board.BoardIterator_Destroy(Iter);
    
    // If no rules found, add defaults
    If N = 0 Then
    Begin
        WriteLn(F, Chr(123) + Q + 'name' + Q + ':' + Q + 'Default Clearance' + Q + ',' + Q + 'type' + Q + ':' + Q + 'clearance' + Q + ',' + Q + 'clearance_mm' + Q + ':0.2' + Chr(125) + ',');
        WriteLn(F, Chr(123) + Q + 'name' + Q + ':' + Q + 'Default Width' + Q + ',' + Q + 'type' + Q + ':' + Q + 'width' + Q + ',' + Q + 'min_width_mm' + Q + ':0.15' + Chr(125) + ',');
        WriteLn(F, Chr(123) + Q + 'name' + Q + ':' + Q + 'Default Via' + Q + ',' + Q + 'type' + Q + ':' + Q + 'via' + Q + ',' + Q + 'min_hole_mm' + Q + ':0.2' + Chr(125));
    End;
    
    WriteLn(F, '],');
    
    // Statistics
    WriteLn(F, Q + 'statistics' + Q + ':' + Chr(123));
    WriteLn(F, Q + 'component_count' + Q + ':' + IntToStr(Board.GetPrimitiveCount(eComponentObject)) + ',');
    WriteLn(F, Q + 'net_count' + Q + ':' + IntToStr(Board.GetPrimitiveCount(eNetObject)) + ',');
    WriteLn(F, Q + 'track_count' + Q + ':' + IntToStr(Board.GetPrimitiveCount(eTrackObject)) + ',');
    WriteLn(F, Q + 'via_count' + Q + ':' + IntToStr(Board.GetPrimitiveCount(eViaObject)) + ',');
    WriteLn(F, Q + 'layer_count' + Q + ':' + IntToStr(Board.LayerStack.LayerCount));
    WriteLn(F, Chr(125));
    
    // End JSON
    WriteLn(F, Chr(125));
    CloseFile(F);
    
    // Now rename the new file to the final name (atomic operation)
    // This avoids I/O error 32 because we're not writing to a locked file
    RetryCount := 0;
    While RetryCount < 10 Do
    Begin
        Try
            // Delete old file if exists
            If FileExists(PCB_INFO_FILE) Then
            Begin
                Try
                    DeleteFile(PCB_INFO_FILE);
                    Sleep(200);
                Except
                    Try
                        RenameFile(PCB_INFO_FILE, PCB_INFO_FILE + '.old');
                        Sleep(200);
                    Except
                        // Continue anyway
                    End;
                End;
            End;
            
            // Rename new file to final name
            RenameFile(S, PCB_INFO_FILE);
            Break;  // Success!
        Except
            Inc(RetryCount);
            If RetryCount < 10 Then
            Begin
                Sleep(500 + (RetryCount * 200));
            End
            Else
            Begin
                // Rename failed, but file exists at S
                WriteRes(True, 'PCB info exported to ' + S + ' (could not rename - file may be locked by MCP server)');
                Exit;
            End;
        End;
    End;
    
    WriteRes(True, 'PCB info exported to altium_pcb_info.json');
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
    
    If Length(Cmd) < 5 Then Exit;  // No command
    
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
        // This includes all data: components, nets, tracks, vias, and DESIGN RULES
        ShowMessage('EagilinsED Command Server Started!' + #13#10 + 
                    'Auto-exporting PCB info (including design rules)...' + #13#10 +
                    'Listening for commands...');
        ExportPCBInfo;
    End;
    
    // Continuously poll for commands
    // Commands can be: move_component, add_track, run_drc, export_pcb_info, etc.
    While ServerRunning Do
    Begin
        // Process any pending commands from agent
        ProcessCommand;
        
        Sleep(200);  // Check every 200ms
        
        // Allow UI to respond
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
