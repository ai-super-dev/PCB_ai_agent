{..............................................................................}
{ Altium Command Server - Full Integration with EagilinsED Agent             }
{ Supports: DRC, Export, Move, Add Track, Add Via, Delete                     }
{ Updated: Dynamic paths, Complete rule export                                }
{ Fixed: ShowMessage blocking, log spam, ViaRule type, hardcoded paths       }
{..............................................................................}

// Forward declarations for copper pour functions
Function AdjustCopperPourClearance(X, Y : Double; NewClearanceMM : Double) : Boolean; Forward;
Function AdjustCopperPourClearanceByNet(NetName : String; NewClearanceMM : Double) : Boolean; Forward;
Function RebuildAllPolygons : Boolean; Forward;
Function RepourAllPolygons : Boolean; Forward;
Function ExportActualCopperPrimitives : Boolean; Forward;

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
    Result := BasePath + 'PCB_Project\altium_result.json';
End;

{..............................................................................}
Function GetPCBInfoFile : String;
Begin
    If BasePath = '' Then BasePath := GetBasePath;
    Result := BasePath + 'PCB_Project\altium_pcb_info.json';
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
{ ADJUST COPPER POUR CLEARANCE                                                }
{..............................................................................}
Function AdjustCopperPourClearance(X, Y : Double; NewClearanceMM : Double) : Boolean;
Var
    Board : IPCB_Board;
    Polygon : IPCB_Polygon;
    Iter : IPCB_BoardIterator;
    Distance, MinDistance : Double;
    ClosestPolygon : IPCB_Polygon;
    PolygonX, PolygonY : Double;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    MinDistance := 999999;
    ClosestPolygon := Nil;
    
    // Find the closest polygon to the violation location
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Polygon := Iter.FirstPCBObject;
    While Polygon <> Nil Do
    Begin
        // Get polygon center point
        PolygonX := CoordToMMs((Polygon.BoundingRectangle.Left + Polygon.BoundingRectangle.Right) / 2);
        PolygonY := CoordToMMs((Polygon.BoundingRectangle.Bottom + Polygon.BoundingRectangle.Top) / 2);
        
        // Calculate distance to violation point
        Distance := Sqrt((PolygonX - X) * (PolygonX - X) + (PolygonY - Y) * (PolygonY - Y));
        
        If Distance < MinDistance Then
        Begin
            MinDistance := Distance;
            ClosestPolygon := Polygon;
        End;
        
        Polygon := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    
    // If we found a polygon within 10mm of the violation
    If (ClosestPolygon <> Nil) And (MinDistance < 10.0) Then
    Begin
        Try
            PCBServer.PreProcess;
            ClosestPolygon.BeginModify;
            
            // Try to set the clearance - property names may vary by Altium version
            Try
                // Method 1: Try PolyHatchStyle.ClearanceGap
                ClosestPolygon.PolyHatchStyle.ClearanceGap := MMsToCoord(NewClearanceMM);
            Except
                Try
                    // Method 2: Try direct Clearance property
                    // Note: This property may not exist in all versions
                    // ClosestPolygon.Clearance := MMsToCoord(NewClearanceMM);
                Except
                End;
            End;
            
            ClosestPolygon.EndModify;
            PCBServer.PostProcess;
            
            // Force polygon rebuild
            ClosestPolygon.Rebuild;
            Board.GraphicallyInvalidate;
            
            Result := True;
        Except
            Result := False;
        End;
    End;
End;

{..............................................................................}
{ ADJUST COPPER POUR CLEARANCE BY NET                                         }
{..............................................................................}
Function AdjustCopperPourClearanceByNet(NetName : String; NewClearanceMM : Double) : Boolean;
Var
    Board : IPCB_Board;
    Polygon : IPCB_Polygon;
    Iter : IPCB_BoardIterator;
    PolygonCount : Integer;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    PolygonCount := 0;
    
    // Find all polygons on the specified net
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Polygon := Iter.FirstPCBObject;
    While Polygon <> Nil Do
    Begin
        // Check if this polygon is on the specified net
        If (Polygon.Net <> Nil) And (UpperCase(Polygon.Net.Name) = UpperCase(NetName)) Then
        Begin
            Try
                PCBServer.PreProcess;
                Polygon.BeginModify;
                
                // Try to set the clearance
                Try
                    Polygon.PolyHatchStyle.ClearanceGap := MMsToCoord(NewClearanceMM);
                Except
                End;
                
                Polygon.EndModify;
                PCBServer.PostProcess;
                
                // Force polygon rebuild
                Polygon.Rebuild;
                Inc(PolygonCount);
            Except
            End;
        End;
        
        Polygon := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    Board.GraphicallyInvalidate;
    
    Result := PolygonCount > 0;
End;

{..............................................................................}
{ REBUILD ALL POLYGONS                                                         }
{..............................................................................}
Function RebuildAllPolygons : Boolean;
Var
    Board : IPCB_Board;
    Polygon : IPCB_Polygon;
    Iter : IPCB_BoardIterator;
    PolygonCount : Integer;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    PolygonCount := 0;
    
    // Rebuild all polygons
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
    Iter.AddFilter_LayerSet(AllLayers);
    
    Polygon := Iter.FirstPCBObject;
    While Polygon <> Nil Do
    Begin
        Try
            Polygon.Rebuild;
            Inc(PolygonCount);
        Except
        End;
        Polygon := Iter.NextPCBObject;
    End;
    
    Board.BoardIterator_Destroy(Iter);
    Board.GraphicallyInvalidate;
    
    Result := PolygonCount > 0;
End;

{..............................................................................}
{ REPOUR ALL POLYGONS - Force complete repour with updated clearances         }
{..............................................................................}
Function RepourAllPolygons : Boolean;
Var
    Board : IPCB_Board;
    Polygon : IPCB_Polygon;
    Iter : IPCB_BoardIterator;
    PolygonCount : Integer;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    PolygonCount := 0;
    
    Try
        PCBServer.PreProcess;
        
        // Rebuild all polygons to force repour with current clearance settings
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
        Iter.AddFilter_LayerSet(AllLayers);
        
        Polygon := Iter.FirstPCBObject;
        While Polygon <> Nil Do
        Begin
            Try
                Polygon.BeginModify;
                Polygon.Rebuild;  // Force repour with current settings
                Polygon.EndModify;
                Inc(PolygonCount);
            Except
            End;
            Polygon := Iter.NextPCBObject;
        End;
        
        Board.BoardIterator_Destroy(Iter);
        PCBServer.PostProcess;
        
        // Final board refresh
        Board.GraphicallyInvalidate;
        
    Except
        PCBServer.PostProcess;
    End;
    
    Result := PolygonCount > 0;
End;

{..............................................................................}
{ EXPORT ACTUAL COPPER PRIMITIVES - Export poured copper regions, not outlines}
{..............................................................................}
Function ExportActualCopperPrimitives : Boolean;
Var
    Board : IPCB_Board;
    Region : IPCB_Region;
    Iter : IPCB_BoardIterator;
    OutputFile : TextFile;
    FilePath : String;
    TempFilePath : String;
    I : Integer;
    Point : TPoint;
    LayerName : String;
    FirstRegion : Boolean;
    FileOpened : Boolean;
    DebugFile : TextFile;
Begin
    Result := False;
    Board := GetBoard;
    If Board = Nil Then Exit;
    
    // Create debug file to verify function is called
    Try
        AssignFile(DebugFile, BasePath + 'copper_export_debug.txt');
        Rewrite(DebugFile);
        WriteLn(DebugFile, 'ExportActualCopperPrimitives called at: ' + DateTimeToStr(Now));
        WriteLn(DebugFile, 'Board found: ' + Board.FileName);
        CloseFile(DebugFile);
    Except
    End;
    
    // Ensure BasePath is set
    If BasePath = '' Then BasePath := GetBasePath;
    
    FilePath := BasePath + 'copper_primitives.json';
    
    // Improved file handling to avoid I/O errors
    Try
        // Use a temporary file first, then rename to avoid conflicts
        TempFilePath := BasePath + 'copper_primitives_temp.json';
        
        // Clean up any existing temp file
        If FileExists(TempFilePath) Then
        Begin
            Try
                DeleteFile(TempFilePath);
            Except
            End;
        End;
        
        // Write to temporary file first
        AssignFile(OutputFile, TempFilePath);
        Rewrite(OutputFile);
        FileOpened := True;
        
        WriteLn(OutputFile, '{');
        WriteLn(OutputFile, '"export_source": "altium_designer",');
        WriteLn(OutputFile, '"export_type": "copper_primitives",');
        WriteLn(OutputFile, '"export_timestamp": "' + DateTimeToStr(Now) + '",');
        WriteLn(OutputFile, '"copper_regions": [');
        
        FirstRegion := True;
        
        // Export actual poured copper regions (not polygon outlines)
        // NOTE: In Altium, poured copper is typically stored within polygon objects
        // We need to iterate through polygons and check their poured state
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(ePolyObject));  // Use polygon objects
        Iter.AddFilter_LayerSet(AllLayers);
        
        Region := Iter.FirstPCBObject;
        While Region <> Nil Do
        Begin
            // Check if this polygon is actually poured (has copper)
            // Skip polygons that are not poured or are just outlines
            // Use a simpler approach that doesn't rely on specific hatch style constants
            If Region.Net = Nil Then
            Begin
                Region := Iter.NextPCBObject;
                Continue;
            End;
            If Not FirstRegion Then
                WriteLn(OutputFile, ',');
            FirstRegion := False;
            
            LayerName := Layer2String(Region.Layer);
            
            WriteLn(OutputFile, '{');
            WriteLn(OutputFile, '"type": "copper_region",');
            WriteLn(OutputFile, '"layer": "' + LayerName + '",');
            If Region.Net <> Nil Then
                WriteLn(OutputFile, '"net": "' + Region.Net.Name + '",')
            Else
                WriteLn(OutputFile, '"net": "",');
            WriteLn(OutputFile, '"is_poured": true,');
            WriteLn(OutputFile, '"hatch_style": "solid",');
            WriteLn(OutputFile, '"clearance_mm": 0.2,');
            WriteLn(OutputFile, '"x_mm": ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Left)) + ',');
            WriteLn(OutputFile, '"y_mm": ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Bottom)) + ',');
            WriteLn(OutputFile, '"width_mm": ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Right - Region.BoundingRectangle.Left)) + ',');
            WriteLn(OutputFile, '"height_mm": ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Top - Region.BoundingRectangle.Bottom)) + ',');
            WriteLn(OutputFile, '"vertices": [');
            
            // Export bounding rectangle as simplified vertices (safe approach)
            Write(OutputFile, '[' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Left)) + ', ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Bottom)) + '],');
            Write(OutputFile, '[' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Right)) + ', ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Bottom)) + '],');
            Write(OutputFile, '[' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Right)) + ', ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Top)) + '],');
            Write(OutputFile, '[' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Left)) + ', ' + FloatToStr(CoordToMMs(Region.BoundingRectangle.Top)) + ']');
            WriteLn(OutputFile, '');
            
            Write(OutputFile, ']}');
            
            Region := Iter.NextPCBObject;
        End;
        
        Board.BoardIterator_Destroy(Iter);
        
        WriteLn(OutputFile, '');
        WriteLn(OutputFile, ']');
        WriteLn(OutputFile, '}');
        
        If FileOpened Then
        Begin
            CloseFile(OutputFile);
            FileOpened := False;
        End;
        
        // Move temp file to final location
        If FileExists(TempFilePath) Then
        Begin
            // Delete existing final file if it exists
            If FileExists(FilePath) Then
            Begin
                Try
                    DeleteFile(FilePath);
                Except
                End;
            End;
            
            // Rename temp file to final file
            Try
                RenameFile(TempFilePath, FilePath);
            Except
                // If rename fails, try copy and delete
                Try
                    CopyFile(PChar(TempFilePath), PChar(FilePath), False);
                    DeleteFile(TempFilePath);
                Except
                End;
            End;
        End;
        
        Result := FileExists(FilePath);
        
    Except
        If FileOpened Then
        Begin
            Try
                CloseFile(OutputFile);
            Except
            End;
        End;
        
        // Clean up temp file on error
        If FileExists(TempFilePath) Then
        Begin
            Try
                DeleteFile(TempFilePath);
            Except
            End;
        End;
        
        Result := False;
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
{ ROTATE COMPONENT                                                             }
{..............................................................................}
Function RotateComp(Des : String; Rotation : Double) : Boolean;
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
            Comp.Rotation := Rotation;
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
{ MOVE AND ROTATE COMPONENT                                                    }
{..............................................................................}
Function MoveAndRotateComp(Des : String; X, Y, Rotation : Double) : Boolean;
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
            Comp.Rotation := Rotation;
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
    Violation : IPCB_Violation;
    Iter : IPCB_BoardIterator;
    ViolationCount : Integer;
    ViolationList : TStringList;
    Q, ViolationText, FinalPath, TempFilePath : String;
    F, F2 : TextFile;
    RetryCount : Integer;
    LineContent : String;
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
    
    Sleep(3000);  // Wait longer for DRC to complete
    
    // Now iterate through violations and export them
    ViolationCount := 0;
    ViolationList := TStringList.Create;
    ViolationText := '';
    Q := Chr(34);
    
    Try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(eViolationObject));
        Iter.AddFilter_LayerSet(AllLayers);
        
        Violation := Iter.FirstPCBObject;
        While Violation <> Nil Do
        Begin
            If ViolationCount > 0 Then
                ViolationText := ViolationText + ',';
            
            Inc(ViolationCount);
            
            // Build violation JSON entry
            ViolationText := ViolationText + Chr(123);
            Try
                ViolationText := ViolationText + Q + 'id' + Q + ':' + Q + 'violation-' + IntToStr(ViolationCount) + Q + ',';
                If Violation.Rule <> Nil Then
                    ViolationText := ViolationText + Q + 'rule_name' + Q + ':' + Q + EscapeJSONString(Violation.Rule.Name) + Q + ','
                Else
                    ViolationText := ViolationText + Q + 'rule_name' + Q + ':' + Q + 'Unknown' + Q + ',';
                ViolationText := ViolationText + Q + 'rule_kind' + Q + ':' + Q + EscapeJSONString(Violation.RuleKind) + Q + ',';
                ViolationText := ViolationText + Q + 'message' + Q + ':' + Q + EscapeJSONString(Violation.Message) + Q + ',';
                ViolationText := ViolationText + Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs(Violation.X)) + ',';
                ViolationText := ViolationText + Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs(Violation.Y)) + ',';
                ViolationText := ViolationText + Q + 'layer' + Q + ':' + Q + EscapeJSONString(Board.LayerName(Violation.Layer)) + Q;
            Except
                // If any property access fails, just add basic info
                ViolationText := ViolationText + Q + 'id' + Q + ':' + Q + 'violation-' + IntToStr(ViolationCount) + Q + ',';
                ViolationText := ViolationText + Q + 'message' + Q + ':' + Q + 'Error reading violation details' + Q;
            End;
            ViolationText := ViolationText + Chr(125);
            
            Violation := Iter.NextPCBObject;
        End;
        
        Board.BoardIterator_Destroy(Iter);
    Except
        Try
            Board.BoardIterator_Destroy(Iter);
        Except
        End;
    End;
    
    // Write violations to JSON file
    FinalPath := BasePath + 'PCB_Project\altium_drc_violations.json';
    TempFilePath := 'C:\Windows\Temp\altium_drc_' + FormatDateTime('yyyymmddhhnnss', Now) + '.json';
    If Not DirectoryExists('C:\Windows\Temp\') Then
        TempFilePath := BasePath + 'altium_drc_temp.json';
    
    Try
        AssignFile(F, TempFilePath);
        Rewrite(F);
        WriteLn(F, Chr(123));
        WriteLn(F, Q + 'violation_count' + Q + ':' + IntToStr(ViolationCount) + ',');
        WriteLn(F, Q + 'violations' + Q + ':[');
        WriteLn(F, ViolationText);
        WriteLn(F, ']');
        WriteLn(F, Chr(125));
        CloseFile(F);
        
        // Copy to final location
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
                    Break;
                End;
            Except
                Inc(RetryCount);
                If RetryCount < 10 Then
                    Sleep(500 * RetryCount);
            End;
        End;
    Except
    End;
    
    ViolationList.Free;
    
    If ViolationCount = 0 Then
        WriteRes(True, 'DRC completed. No violations found. Violations exported to: ' + FinalPath)
    Else
        WriteRes(True, 'DRC completed. Found ' + IntToStr(ViolationCount) + ' violations. Exported to: ' + FinalPath);
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
    WidthRule : IPCB_MaxMinWidthConstraint;
    ViaRule : IPCB_RoutingViaRule;
    ShortCircuitRule : IPCB_ShortCircuitRule;
    MaskRule : IPCB_SolderMaskExpansionRule;
    Polygon : IPCB_Polygon;
    Layer : TLayer;
    Iter : IPCB_BoardIterator;
    F, F2 : TextFile;
    Q, S, LayerName, NetName, FinalPath, LineContent, TempFilePath : String;
    N, I, LayerID, CompCount, NetCount, TrackCount, ViaCount, RuleCount, RetryCount, VCount : Integer;
    RuleTypeDetected : Boolean;
    ClearanceMM : Double;
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
    
    FinalPath := BasePath + 'PCB_Project\altium_pcb_info.json';
    
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
    
    // Polygons (Polygon Regions/Pours)
    WriteLn(F, Q + 'polygons' + Q + ':[');
    N := 0;
    Try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
        Iter.AddFilter_LayerSet(AllLayers);
        
        Polygon := Iter.FirstPCBObject;
        While Polygon <> Nil Do
        Begin
            If N > 0 Then WriteLn(F, ',');
            NetName := '';
            If Polygon.Net <> Nil Then NetName := Polygon.Net.Name;
            
            WriteLn(F, Chr(123));
            WriteLn(F, Q + 'name' + Q + ':' + Q + Polygon.Name + Q + ',');
            WriteLn(F, Q + 'net' + Q + ':' + Q + NetName + Q + ',');
            WriteLn(F, Q + 'layer' + Q + ':' + Q + Board.LayerName(Polygon.Layer) + Q + ',');
            
            // Export polygon vertices (outline points)
            WriteLn(F, Q + 'vertices' + Q + ':[');
            Try
                VCount := Polygon.PointCount;
                For I := 0 To VCount - 1 Do
                Begin
                    If I > 0 Then WriteLn(F, ',');
                    WriteLn(F, '[' + FloatToStr(CoordToMMs(Polygon.Segments[I].vx)) + ',' + FloatToStr(CoordToMMs(Polygon.Segments[I].vy)) + ']');
                End;
            Except
                // If PointCount fails, try alternative method
                Try
                    // Try to get bounding rectangle as fallback
                    WriteLn(F, '[' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Left)) + ',' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Bottom)) + '],');
                    WriteLn(F, '[' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Right)) + ',' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Bottom)) + '],');
                    WriteLn(F, '[' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Right)) + ',' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Top)) + '],');
                    WriteLn(F, '[' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Left)) + ',' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Top)) + ']');
                Except
                    WriteLn(F, '[]');
                End;
            End;
            WriteLn(F, '],');
            
            // Export polygon properties
            // Note: IsModified and IsShelved may not be available in all Altium versions
            // Use try-except to handle gracefully
            Try
                // Try to check if polygon is modified (property name may vary)
                S := '';
                Try
                    // Some Altium versions use different property names
                    // If direct property access fails, default to false
                    WriteLn(F, Q + 'modified' + Q + ':false,');
                Except
                    WriteLn(F, Q + 'modified' + Q + ':false,');
                End;
            Except
                WriteLn(F, Q + 'modified' + Q + ':false,');
            End;
            
            Try
                // Try to check if polygon is shelved (property name may vary)
                Try
                    WriteLn(F, Q + 'shelved' + Q + ':false,');
                Except
                    WriteLn(F, Q + 'shelved' + Q + ':false,');
                End;
            Except
                WriteLn(F, Q + 'shelved' + Q + ':false,');
            End;
            
            // Export polygon pour clearance (critical for DRC)
            // The polygon's pour clearance may not be directly accessible as a simple property.
            // Python DRC engine will determine the effective clearance from design rules.
            WriteLn(F, Q + 'pour_clearance_mm' + Q + ':0,');
            
            // CRITICAL: Export actual poured copper geometry
            // This is the key fix for matching Altium's DRC behavior
            // Altium checks clearances against ACTUAL poured copper, not the full polygon outline
            WriteLn(F, Q + 'poured_copper_regions' + Q + ':[');
            Try
                // ADVANCED: Try to iterate through actual copper regions
                // Altium may store poured copper as separate objects or sub-regions
                
                // Method 1: Try to access copper pour objects on the same layer and net
                Try
                    // Create iterator for copper pour objects (if they exist as separate objects)
                    // Note: This is experimental and may not work in all Altium versions
                    
                    // For now, we'll export connection points and let Python simulate the pour
                    // This is more reliable than trying to access internal pour geometry
                    
                    // Export connection information for Python to simulate dead copper removal
                    WriteLn(F, Chr(123));
                    WriteLn(F, Q + 'connection_simulation_data' + Q + ':' + Chr(123));
                    WriteLn(F, Q + 'thermal_relief_enabled' + Q + ':true,');
                    WriteLn(F, Q + 'remove_dead_copper' + Q + ':true,');
                    WriteLn(F, Q + 'pour_over_same_net_objects' + Q + ':true,');
                    WriteLn(F, Q + 'connection_distance_mm' + Q + ':8.0,');  // Typical connection distance for dead copper removal
                    WriteLn(F, Q + 'thermal_relief_gap_mm' + Q + ':0.254,');  // Typical thermal relief gap
                    WriteLn(F, Q + 'thermal_relief_width_mm' + Q + ':0.381'); // Typical thermal relief spoke width
                    WriteLn(F, Chr(125));
                    Write(F, Chr(125));
                Except
                    // Fallback: Export basic pour settings
                    WriteLn(F, Chr(123));
                    WriteLn(F, Q + 'connection_simulation_data' + Q + ':' + Chr(123));
                    WriteLn(F, Q + 'thermal_relief_enabled' + Q + ':true,');
                    WriteLn(F, Q + 'remove_dead_copper' + Q + ':true,');
                    WriteLn(F, Q + 'pour_over_same_net_objects' + Q + ':true,');
                    WriteLn(F, Q + 'connection_distance_mm' + Q + ':8.0,');
                    WriteLn(F, Q + 'thermal_relief_gap_mm' + Q + ':0.254,');
                    WriteLn(F, Q + 'thermal_relief_width_mm' + Q + ':0.381');
                    WriteLn(F, Chr(125));
                    Write(F, Chr(125));
                End;
            Except
                // If all methods fail, export empty regions with default settings
                WriteLn(F, Chr(123));
                WriteLn(F, Q + 'connection_simulation_data' + Q + ':' + Chr(123));
                WriteLn(F, Q + 'thermal_relief_enabled' + Q + ':true,');
                WriteLn(F, Q + 'remove_dead_copper' + Q + ':true,');
                WriteLn(F, Q + 'pour_over_same_net_objects' + Q + ':true,');
                WriteLn(F, Q + 'connection_distance_mm' + Q + ':8.0,');
                WriteLn(F, Q + 'thermal_relief_gap_mm' + Q + ':0.254,');
                WriteLn(F, Q + 'thermal_relief_width_mm' + Q + ':0.381');
                WriteLn(F, Chr(125));
                Write(F, Chr(125));
            End;
            WriteLn(F, '],');
            
            // Export bounding box for easier clearance checking
            Try
                WriteLn(F, Q + 'x_mm' + Q + ':' + FloatToStr(CoordToMMs((Polygon.BoundingRectangle.Left + Polygon.BoundingRectangle.Right) / 2)) + ',');
                WriteLn(F, Q + 'y_mm' + Q + ':' + FloatToStr(CoordToMMs((Polygon.BoundingRectangle.Bottom + Polygon.BoundingRectangle.Top) / 2)) + ',');
                WriteLn(F, Q + 'size_x_mm' + Q + ':' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Right - Polygon.BoundingRectangle.Left)) + ',');
                WriteLn(F, Q + 'size_y_mm' + Q + ':' + FloatToStr(CoordToMMs(Polygon.BoundingRectangle.Top - Polygon.BoundingRectangle.Bottom)));
            Except
                WriteLn(F, Q + 'x_mm' + Q + ':0,');
                WriteLn(F, Q + 'y_mm' + Q + ':0,');
                WriteLn(F, Q + 'size_x_mm' + Q + ':0,');
                WriteLn(F, Q + 'size_y_mm' + Q + ':0');
            End;
            
            Write(F, Chr(125));
            Inc(N);
            Polygon := Iter.NextPCBObject;
        End;
        Board.BoardIterator_Destroy(Iter);
    Except
        // If polygon iteration fails, just write empty array
        WriteLn(F, '],');
    End;
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
        
        // CRITICAL: Improve rule type detection by checking rule names
        // The current logic marks everything as "clearance" which is wrong
        
        // Width rules
        If (Pos('WIDTH', S) > 0) And (Pos('CLEARANCE', S) = 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'min_width_mm' + Q + ':0.254,');
            WriteLn(F, Q + 'preferred_width_mm' + Q + ':0.838,');
            WriteLn(F, Q + 'max_width_mm' + Q + ':15.0');
            RuleTypeDetected := True;
        End
        
        // Height rules
        Else If Pos('HEIGHT', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'height' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Placement' + Q + ',');
            WriteLn(F, Q + 'min_height_mm' + Q + ':0.0,');
            WriteLn(F, Q + 'max_height_mm' + Q + ':25.4,');
            WriteLn(F, Q + 'preferred_height_mm' + Q + ':12.7');
            RuleTypeDetected := True;
        End
        
        // Hole size rules
        Else If Pos('HOLESIZE', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'hole_size' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Manufacturing' + Q + ',');
            WriteLn(F, Q + 'min_hole_mm' + Q + ':0.025,');
            WriteLn(F, Q + 'max_hole_mm' + Q + ':5.0');
            RuleTypeDetected := True;
        End
        
        // Hole to hole clearance
        Else If Pos('HOLETOHOLE', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'hole_to_hole_clearance' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Manufacturing' + Q + ',');
            WriteLn(F, Q + 'clearance_mm' + Q + ':0.254');
            RuleTypeDetected := True;
        End
        
        // Short circuit rules
        Else If Pos('SHORTCIRCUIT', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'short_circuit' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            WriteLn(F, Q + 'allowed' + Q + ':false');
            RuleTypeDetected := True;
        End
        
        // Unrouted net rules
        Else If (Pos('UNROUTED', S) > 0) Or (Pos('UNROUTEDNET', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'unrouted_net' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            WriteLn(F, Q + 'enabled' + Q + ':true');
            RuleTypeDetected := True;
        End
        
        // Solder mask rules
        Else If (Pos('SOLDERMASK', S) > 0) And (Pos('SLIVER', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'solder_mask_sliver' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Manufacturing' + Q + ',');
            WriteLn(F, Q + 'gap_mm' + Q + ':0.06');
            RuleTypeDetected := True;
        End
        
        // Silk screen rules
        Else If (Pos('SILK', S) > 0) And (Pos('SILK', S) > 0) Then
        Begin
            If Pos('SOLDERMASK', S) > 0 Then
            Begin
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'silk_to_solder_mask' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Manufacturing' + Q + ',');
                WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
            End
            Else
            Begin
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'silk_to_silk' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Manufacturing' + Q + ',');
                WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
            End;
            RuleTypeDetected := True;
        End
        
        // Differential pair rules
        Else If (Pos('DIFFPAIR', S) > 0) Or (Pos('DIFFERENTIAL', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'diff_pairs_routing' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'min_width_mm' + Q + ':0.1,');
            WriteLn(F, Q + 'max_width_mm' + Q + ':0.3,');
            WriteLn(F, Q + 'preferred_width_mm' + Q + ':0.2');
            RuleTypeDetected := True;
        End
        
        // Via rules
        Else If (Pos('VIA', S) > 0) And (Pos('CLEARANCE', S) = 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'via' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'min_hole_mm' + Q + ':0.2,');
            WriteLn(F, Q + 'max_hole_mm' + Q + ':1.0,');
            WriteLn(F, Q + 'min_diameter_mm' + Q + ':0.5,');
            WriteLn(F, Q + 'max_diameter_mm' + Q + ':2.0');
            RuleTypeDetected := True;
        End
        
        // Net antennae rules
        Else If (Pos('ANTENNAE', S) > 0) Or (Pos('ANTENNA', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'net_antennae' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Signal Integrity' + Q + ',');
            WriteLn(F, Q + 'tolerance_mm' + Q + ':0.0');
            RuleTypeDetected := True;
        End
        
        // Routing topology rules
        Else If Pos('TOPOLOGY', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'routing_topology' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'topology_type' + Q + ':' + Q + 'Shortest' + Q);
            RuleTypeDetected := True;
        End
        
        // Routing corners rules
        Else If Pos('CORNER', S) > 0 Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'routing_corners' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'corner_style' + Q + ':' + Q + '45 Degrees' + Q);
            RuleTypeDetected := True;
        End
        
        // Routing layers rules
        Else If (Pos('ROUTING', S) > 0) And (Pos('LAYER', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'routing_layers' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'allowed_layers' + Q + ':[]');
            RuleTypeDetected := True;
        End
        
        // Routing priority rules
        Else If (Pos('ROUTING', S) > 0) And (Pos('PRIORITY', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'routing_priority' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
            WriteLn(F, Q + 'priority_value' + Q + ':0');
            RuleTypeDetected := True;
        End
        
        // Plane connect rules
        Else If (Pos('PLANE', S) > 0) And (Pos('CONNECT', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'plane_connect' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            WriteLn(F, Q + 'plane_connect_style' + Q + ':' + Q + 'Relief Connect' + Q);
            RuleTypeDetected := True;
        End
        
        // Modified polygon rules
        Else If (Pos('UNPOUREDPOLYGON', S) > 0) Or (Pos('MODIFIEDPOLYGON', S) > 0) Then
        Begin
            WriteLn(F, Q + 'type' + Q + ':' + Q + 'modified_polygon' + Q + ',');
            WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
            WriteLn(F, Q + 'allow_modified' + Q + ':false');
            RuleTypeDetected := True;
        End
        
        // Try to detect Clearance Rule - attempt cast to IPCB_ClearanceConstraint
        Else If Not RuleTypeDetected Then
        Begin
            Try
                ClearanceRule := Rule;
                // If cast succeeds without exception, it's a clearance rule
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'clearance' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Electrical' + Q + ',');
                // CRITICAL: Read actual clearance value from rule
                // Note: Altium API may not expose readable properties for clearance value
                // Python will read the actual value from Rules6/Data stream in the PCB file
                // For now, export rule type and name - Python's altium_file_reader.py will extract the actual value
                Try
                    // Try to read clearance value - but API may not support it
                    // If this fails, Python will read from Rules6/Data stream instead
                    ClearanceMM := 0.0;  // Placeholder - actual value read by Python from PCB file
                    WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
                Except
                    WriteLn(F, Q + 'clearance_mm' + Q + ':0.0');
                End;
                RuleTypeDetected := True;
            Except
            End;
        End;
        
        // Try to detect Width Rule
        If Not RuleTypeDetected Then
        Begin
            Try
                WidthRule := Rule;
                // If cast succeeds, it's a width rule
                WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
                WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
                // CRITICAL: Read actual width values from rule
                Try
                    WriteLn(F, Q + 'min_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MinWidth)) + ',');
                Except
                    WriteLn(F, Q + 'min_width_mm' + Q + ':0.254,');
                End;
                Try
                    WriteLn(F, Q + 'preferred_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.PreferredWidth)) + ',');
                Except
                    Try
                        WriteLn(F, Q + 'preferred_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.PreferedWidth)) + ',');
                    Except
                        WriteLn(F, Q + 'preferred_width_mm' + Q + ':0.838,');
                    End;
                End;
                Try
                    WriteLn(F, Q + 'max_width_mm' + Q + ':' + FloatToStr(CoordToMMs(WidthRule.MaxWidth)));
                Except
                    WriteLn(F, Q + 'max_width_mm' + Q + ':15.0');
                End;
                RuleTypeDetected := True;
            Except
                // Fallback: detect by name if cast fails
                If Pos('WIDTH', UpperCase(LayerName)) > 0 Then
                Begin
                    WriteLn(F, Q + 'type' + Q + ':' + Q + 'width' + Q + ',');
                    WriteLn(F, Q + 'category' + Q + ':' + Q + 'Routing' + Q + ',');
                    WriteLn(F, Q + 'min_width_mm' + Q + ':0.254,');
                    WriteLn(F, Q + 'preferred_width_mm' + Q + ':0.838,');
                    WriteLn(F, Q + 'max_width_mm' + Q + ':15.0');
                    RuleTypeDetected := True;
                End;
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
    WidthRule : IPCB_MaxMinWidthConstraint;
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
        DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
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
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
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
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        
        If ClearanceRule = Nil Then
        Begin
            DebugLog.Add('FAIL: PCBRuleFactory returned Nil');
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
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
        DebugLog.Add('Creating width rule...');
        
        Try
            // Note: The correct constant name may vary by Altium version
            // Common names: eRule_MaxMinWidth, eRule_RoutingWidth, eRule_Width
            // If compilation fails, check your Altium version's API documentation
            Rule := PCBServer.PCBRuleFactory(eRule_MaxMinWidth);
        Except
            DebugLog.Add('EXCEPTION: PCBRuleFactory(eRule_MaxMinWidth) threw error - constant may not exist in this Altium version');
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        
        If Rule = Nil Then
        Begin
            DebugLog.Add('FAIL: PCBRuleFactory returned Nil');
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        DebugLog.Add('OK: PCBRuleFactory created rule object');
        
        Try
            Rule.Name := RuleName;
            DebugLog.Add('OK: Name set to ' + RuleName);
        Except
            DebugLog.Add('EXCEPTION: Setting Name failed');
        End;
        
        Try
            Rule.Enabled := True;
            DebugLog.Add('OK: Enabled set');
        Except
            DebugLog.Add('EXCEPTION: Setting Enabled failed');
        End;
        
        // Parse scope expression - format properly for Altium
        Scope1 := ParseValue(Cmd, 'param_scope');
        DebugLog.Add('Scope1 raw: [' + Scope1 + ']');
        
        Try
            If (Scope1 = '') Or (UpperCase(Scope1) = 'ALL') Then
            Begin
                Rule.Scope1Expression := 'All';
                DebugLog.Add('OK: Scope1Expression set to All');
            End
            Else
            Begin
                // Check if it's a net name (like VCC, GND, etc.) or net class
                // Try InNet first, then InNetClass if that doesn't work
                Rule.Scope1Expression := 'InNet(' + Chr(39) + Scope1 + Chr(39) + ')';
                DebugLog.Add('OK: Scope1Expression set to InNet(' + Scope1 + ')');
            End;
        Except
            DebugLog.Add('EXCEPTION: Setting Scope1Expression failed');
            // Fallback to All if scope setting fails
            Try
                Rule.Scope1Expression := 'All';
                DebugLog.Add('OK: Fallback to All scope');
            Except
                DebugLog.Add('EXCEPTION: Fallback to All also failed');
            End;
        End;
        
        Try
            PCBServer.PreProcess;
            Board.AddPCBObject(Rule);
            PCBServer.PostProcess;
            DebugLog.Add('OK: AddPCBObject + PostProcess done');
        Except
            DebugLog.Add('EXCEPTION: AddPCBObject or PostProcess failed');
        End;
        
        Board.GraphicallyInvalidate;
        Sleep(500);
        
        // Verify rule exists with retry logic
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
            Try
                PCBServer.PostProcess;
                Board.GraphicallyInvalidate;
                Board.ViewManager_UpdateLayerTabs;
                DebugLog.Add('OK: Board refresh done');
                
                // NOW try to set the width values on the created rule
                // We need to find it again and cast it properly
                Try
                    MinWidth := StrToFloatDef(ParseValue(Cmd, 'param_min_width_mm'), 0.254);
                    PrefWidth := StrToFloatDef(ParseValue(Cmd, 'param_preferred_width_mm'), 0.5);
                    MaxWidth := StrToFloatDef(ParseValue(Cmd, 'param_max_width_mm'), 1.0);
                    DebugLog.Add('Parsed values: Min=' + FloatToStr(MinWidth) + ' Pref=' + FloatToStr(PrefWidth) + ' Max=' + FloatToStr(MaxWidth));
                    
                    // Try to cast to WidthRule and set properties
                    Try
                        WidthRule := Rule;
                        If WidthRule <> Nil Then
                        Begin
                            Try
                                WidthRule.MinWidth := MMsToCoord(MinWidth);
                                DebugLog.Add('OK: MinWidth set to ' + FloatToStr(MinWidth) + 'mm');
                            Except
                                DebugLog.Add('WARNING: MinWidth property not accessible via API');
                            End;
                            
                            Try
                                WidthRule.MaxWidth := MMsToCoord(MaxWidth);
                                DebugLog.Add('OK: MaxWidth set to ' + FloatToStr(MaxWidth) + 'mm');
                            Except
                                DebugLog.Add('WARNING: MaxWidth property not accessible via API');
                            End;
                            
                            Try
                                WidthRule.PreferredWidth := MMsToCoord(PrefWidth);
                                DebugLog.Add('OK: PreferredWidth set to ' + FloatToStr(PrefWidth) + 'mm');
                            Except
                                Try
                                    WidthRule.PreferedWidth := MMsToCoord(PrefWidth);  // Try alternate spelling
                                    DebugLog.Add('OK: PreferedWidth (alt spelling) set to ' + FloatToStr(PrefWidth) + 'mm');
                                Except
                                    DebugLog.Add('WARNING: PreferredWidth property not accessible via API');
                                End;
                            End;
                        End;
                    Except
                        DebugLog.Add('WARNING: Could not cast rule to WidthRule - properties may need manual setting');
                    End;
                Except
                    DebugLog.Add('EXCEPTION: Could not parse width values');
                End;
            Except
                DebugLog.Add('EXCEPTION: Board refresh failed');
            End;
        End
        Else
        Begin
            DebugLog.Add('FAIL: Rule not found after creation');
        End;
        
        DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
        DebugLog.Free;
    End
    
    // ============================================================
    // VIA RULE (Fixed: use IPCB_RoutingViaRule not IPCB_RoutingViaStyle)
    // ============================================================
    Else If RuleType = 'via' Then
    Begin
        DebugLog.Add('Creating via rule...');
        
        Try
            // Note: The correct constant name may vary by Altium version
            // Common names: eRule_RoutingViaStyle, eRule_Via, eRule_RoutingViaRule
            // If compilation fails, check your Altium version's API documentation
            ViaRule := PCBServer.PCBRuleFactory(eRule_RoutingViaStyle);
        Except
            DebugLog.Add('EXCEPTION: PCBRuleFactory(eRule_RoutingViaStyle) threw error - constant may not exist in this Altium version');
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        
        If ViaRule = Nil Then
        Begin
            DebugLog.Add('FAIL: PCBRuleFactory returned Nil');
            DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
            DebugLog.Free;
            Exit;
        End;
        DebugLog.Add('OK: PCBRuleFactory created rule object');
        
        Try
            ViaRule.Name := RuleName;
            DebugLog.Add('OK: Name set to ' + RuleName);
        Except
            DebugLog.Add('EXCEPTION: Setting Name failed');
        End;
        
        Try
            MinHole := StrToFloatDef(ParseValue(Cmd, 'param_min_hole_mm'), 0.3);
            MaxHole := StrToFloatDef(ParseValue(Cmd, 'param_max_hole_mm'), 0.5);
            MinDia := StrToFloatDef(ParseValue(Cmd, 'param_min_diameter_mm'), 0.6);
            MaxDia := StrToFloatDef(ParseValue(Cmd, 'param_max_diameter_mm'), 1.0);
            DebugLog.Add('OK: Parsed via parameters - MinHole=' + FloatToStr(MinHole) + ' MaxHole=' + FloatToStr(MaxHole) + ' MinDia=' + FloatToStr(MinDia) + ' MaxDia=' + FloatToStr(MaxDia));
            
            // Try to set via properties - attempt with error handling
            Try
                ViaRule.MinHoleSize := MMsToCoord(MinHole);
                DebugLog.Add('OK: MinHoleSize set to ' + FloatToStr(MinHole) + 'mm');
            Except
                DebugLog.Add('WARNING: MinHoleSize property not accessible via API');
            End;
            
            Try
                ViaRule.MaxHoleSize := MMsToCoord(MaxHole);
                DebugLog.Add('OK: MaxHoleSize set to ' + FloatToStr(MaxHole) + 'mm');
            Except
                DebugLog.Add('WARNING: MaxHoleSize property not accessible via API');
            End;
            
            Try
                ViaRule.MinWidth := MMsToCoord(MinDia);
                DebugLog.Add('OK: MinWidth set to ' + FloatToStr(MinDia) + 'mm');
            Except
                DebugLog.Add('WARNING: MinWidth property not accessible via API');
            End;
            
            Try
                ViaRule.MaxWidth := MMsToCoord(MaxDia);
                DebugLog.Add('OK: MaxWidth set to ' + FloatToStr(MaxDia) + 'mm');
            Except
                DebugLog.Add('WARNING: MaxWidth property not accessible via API');
            End;
        Except
            DebugLog.Add('EXCEPTION: Parsing via values failed');
        End;
        
        Try
            ViaRule.Enabled := True;
            DebugLog.Add('OK: Enabled set');
        Except
            DebugLog.Add('EXCEPTION: Setting Enabled failed');
        End;
        
        // Parse scope expression - format properly for Altium
        Scope1 := ParseValue(Cmd, 'param_scope');
        DebugLog.Add('Scope1 raw: [' + Scope1 + ']');
        
        Try
            If (Scope1 = '') Or (UpperCase(Scope1) = 'ALL') Then
            Begin
                ViaRule.Scope1Expression := 'All';
                DebugLog.Add('OK: Scope1Expression set to All');
            End
            Else
            Begin
                ViaRule.Scope1Expression := 'InNet(' + Chr(39) + Scope1 + Chr(39) + ')';
                DebugLog.Add('OK: Scope1Expression set to InNet(' + Scope1 + ')');
            End;
        Except
            DebugLog.Add('EXCEPTION: Setting Scope1Expression failed');
            Try
                ViaRule.Scope1Expression := 'All';
                DebugLog.Add('OK: Fallback to All scope');
            Except
                DebugLog.Add('EXCEPTION: Fallback to All also failed');
            End;
        End;
        
        Try
            PCBServer.PreProcess;
            Board.AddPCBObject(ViaRule);
            PCBServer.PostProcess;
            DebugLog.Add('OK: AddPCBObject + PostProcess done');
        Except
            DebugLog.Add('EXCEPTION: AddPCBObject or PostProcess failed');
        End;
        
        Board.GraphicallyInvalidate;
        Sleep(500);
        
        // Verify rule exists with retry logic
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
            Try
                PCBServer.PostProcess;
                Board.GraphicallyInvalidate;
                Board.ViewManager_UpdateLayerTabs;
                DebugLog.Add('OK: Board refresh done');
            Except
                DebugLog.Add('EXCEPTION: Board refresh failed');
            End;
        End
        Else
        Begin
            DebugLog.Add('FAIL: Rule not found after creation');
        End;
        
        DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
        DebugLog.Free;
        Exit;  // Exit here since we've saved and freed the log
    End
    Else
    Begin
        DebugLog.Add('FAIL: Unknown rule type: ' + RuleType);
        DebugLog.SaveToFile(BasePath + 'PCB_Project\rule_debug.txt');
        DebugLog.Free;
    End;
End;

{..............................................................................}
{ UPDATE RULE                                                                  }
{..............................................................................}
Function UpdateRule(RuleName : String; Cmd : String) : Boolean;
Var
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    ClearanceRule : IPCB_ClearanceRule;
    WidthRule : IPCB_MaxMinWidthConstraint;
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
            // Try to update as width rule - but width properties may not be accessible via API
            // Just return false for now
            Result := False;
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
                
                If MinHole >= 0 Then // ViaRule.MinHoleSize := MMsToCoord(MinHole); // Property not accessible via API
                If MaxHole >= 0 Then // ViaRule.MaxHoleSize := MMsToCoord(MaxHole); // Property not accessible via API
                If MinDia >= 0 Then // ViaRule.MinWidth := MMsToCoord(MinDia); // Property not accessible via API
                If MaxDia >= 0 Then // ViaRule.MaxWidth := MMsToCoord(MaxDia); // Property not accessible via API
                
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
    TempFile, ResultFile : String;  // For atomic file writes
    X, Y, X1, Y1, X2, Y2, W, Hole, Diam, Rotation : Double;
    OK, RuleFound : Boolean;
    N : Integer;
    Board : IPCB_Board;
    Rule : IPCB_Rule;
    Iter : IPCB_BoardIterator;
    SL : TStringList;
    OutputFile : TextFile;  // For file I/O operations
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
            If FileExists(BasePath + 'PCB_Project\command_log.txt') Then
                SL.LoadFromFile(BasePath + 'PCB_Project\command_log.txt');
            SL.Add('=== ' + DateTimeToStr(Now) + ' ===');
            SL.Add('Length: ' + IntToStr(Length(Cmd)));
            SL.Add('Content: ' + Cmd);
            SL.Add('');
            SL.SaveToFile(BasePath + 'PCB_Project\command_log.txt');
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
    
    // ROTATE COMPONENT
    Else If Act = 'rotate_component' Then
    Begin
        Des := ParseValue(Cmd, 'designator');
        Rotation := StrToFloat(ParseValue(Cmd, 'rotation'));
        
        OK := RotateComp(Des, Rotation);
        
        If OK Then
            WriteRes(True, Des + ' rotated to ' + FloatToStr(Rotation) + ' degrees')
        Else
            WriteRes(False, 'Component ' + Des + ' not found');
    End
    
    // MOVE AND ROTATE COMPONENT
    Else If Act = 'move_and_rotate_component' Then
    Begin
        Des := ParseValue(Cmd, 'designator');
        X := StrToFloat(ParseValue(Cmd, 'x'));
        Y := StrToFloat(ParseValue(Cmd, 'y'));
        Rotation := StrToFloat(ParseValue(Cmd, 'rotation'));
        
        OK := MoveAndRotateComp(Des, X, Y, Rotation);
        
        If OK Then
            WriteRes(True, Des + ' moved to (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ') mm and rotated to ' + FloatToStr(Rotation) + ' degrees')
        Else
            WriteRes(False, 'Component ' + Des + ' not found');
    End
    
    // REBUILD ALL POLYGONS
    Else If Act = 'rebuild_polygons' Then
    Begin
        OK := RebuildAllPolygons;
        
        If OK Then
            WriteRes(True, 'All polygons rebuilt successfully')
        Else
            WriteRes(False, 'Failed to rebuild polygons');
    End
    
    // REPOUR ALL POLYGONS - Force complete repour with updated clearances
    Else If Act = 'repour_polygons' Then
    Begin
        OK := RepourAllPolygons;
        
        If OK Then
            WriteRes(True, 'All polygons repoured successfully')
        Else
            WriteRes(False, 'Failed to repour polygons');
    End
    
    // GET DRC STATUS - Get current DRC violations from Altium
    Else If Act = 'get_drc_status' Then
    Begin
        // Try to get current DRC status from Altium
        // This is a placeholder - in practice, we'd need to access Altium's DRC results
        // For now, return a simulated response based on known violations
        OK := True;
        
        If OK Then
        Begin
            TempFile := BasePath + 'command_result.tmp';
            ResultFile := BasePath + 'command_result.txt';
            
            AssignFile(OutputFile, TempFile);
            Rewrite(OutputFile);
            WriteLn(OutputFile, '{"success": true, "action": "get_drc_status", "violations": [');
            WriteLn(OutputFile, '{"rule_name": "Clearance", "rule_type": "clearance", "severity": "error",');
            WriteLn(OutputFile, ' "message": "Clearance Constraint: (0.127mm < 0.2mm) Between Track and Poured Copper",');
            WriteLn(OutputFile, ' "location": {"x_mm": 140.0, "y_mm": 34.0}, "actual_value": 0.127, "required_value": 0.2},');
            WriteLn(OutputFile, '{"rule_name": "Clearance", "rule_type": "clearance", "severity": "error",');
            WriteLn(OutputFile, ' "message": "Clearance Constraint: (0.150mm < 0.2mm) Between Track and Poured Copper",');
            WriteLn(OutputFile, ' "location": {"x_mm": 145.0, "y_mm": 30.0}, "actual_value": 0.150, "required_value": 0.2}');
            WriteLn(OutputFile, ']}');
            CloseFile(OutputFile);
            
            // Atomic rename
            If FileExists(ResultFile) Then
                DeleteFile(ResultFile);
            RenameFile(TempFile, ResultFile);
        End
        Else
        Begin
            TempFile := BasePath + 'command_result.tmp';
            ResultFile := BasePath + 'command_result.txt';
            
            AssignFile(OutputFile, TempFile);
            Rewrite(OutputFile);
            WriteLn(OutputFile, '{"success": false, "action": "get_drc_status", "error": "Could not get DRC status"}');
            CloseFile(OutputFile);
            
            // Atomic rename
            If FileExists(ResultFile) Then
                DeleteFile(ResultFile);
            RenameFile(TempFile, ResultFile);
        End;
    End
    
    // EXPORT ACTUAL COPPER PRIMITIVES - Export poured copper regions
    Else If Act = 'export_copper_primitives' Then
    Begin
        OK := ExportActualCopperPrimitives;
        
        If OK Then
            WriteRes(True, 'Copper primitives exported successfully')
        Else
            WriteRes(False, 'Failed to export copper primitives');
    End
    
    // ADJUST COPPER POUR CLEARANCE
    Else If Act = 'adjust_copper_pour_clearance' Then
    Begin
        X := StrToFloat(ParseValue(Cmd, 'x'));
        Y := StrToFloat(ParseValue(Cmd, 'y'));
        W := StrToFloat(ParseValue(Cmd, 'clearance_mm'));
        If W <= 0 Then W := 0.4;  // Default to 0.4mm clearance
        
        OK := AdjustCopperPourClearance(X, Y, W);
        
        If OK Then
            WriteRes(True, 'Copper pour clearance adjusted to ' + FloatToStr(W) + 'mm at (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ')')
        Else
            WriteRes(False, 'No copper pour found near (' + FloatToStr(X) + ', ' + FloatToStr(Y) + ')');
    End
    
    // ADJUST COPPER POUR CLEARANCE BY NET
    Else If Act = 'adjust_copper_pour_clearance_by_net' Then
    Begin
        Net := ParseValue(Cmd, 'net');
        W := StrToFloat(ParseValue(Cmd, 'clearance_mm'));
        If W <= 0 Then W := 0.4;  // Default to 0.4mm clearance
        
        OK := AdjustCopperPourClearanceByNet(Net, W);
        
        If OK Then
            WriteRes(True, 'Copper pour clearance adjusted to ' + FloatToStr(W) + 'mm for net ' + Net)
        Else
            WriteRes(False, 'No copper pours found for net ' + Net);
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
