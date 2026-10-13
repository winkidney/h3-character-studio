extends "res://tools/lighting-control/cardinal_scene.gd"
## Uses the same scene and saved values as the interactive renderer.
var output := ""
var selection: Dictionary = {}
var shot_frame := 0
var trajectory: Array[Dictionary] = []

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--lighting-params="):
            selection=JSON.parse_string(FileAccess.get_file_as_string(arg.trim_prefix("--lighting-params=")))
            params=selection.params
        if arg.begins_with("--jade-output="):output=arg.trim_prefix("--jade-output=")
    if selection.is_empty() or output.is_empty():
        push_error("Recording requires a saved lighting selection and output directory")
        quit(2)
        return
    DirAccess.make_dir_recursive_absolute(output)
    super._initialize()

func _process(_delta: float) -> bool:
    if not active:return false
    if shot_frame==0:apply_parameters()
    var direction_frames:=int(round(float(params.direction_seconds)*30))
    var total_frames:=direction_frames*4
    var phase:=mini(3,shot_frame/direction_frames)
    var seconds:=shot_frame/30.0
    var offset: Vector3=light_offsets()[phase]
    var local_frame:=shot_frame%direction_frames
    if phase>0 and local_frame<24:
        offset=light_offsets()[phase-1].lerp(offset,smoothstep(0.0,1.0,local_frame/24.0))
    pose_and_light(seconds,offset,false)
    if shot_frame<total_frames:
        trajectory.append({"frame":shot_frame,"direction":phase,"animation_frame":actors[0].animation_frame,"clay_animation_frame":actors[1].animation_frame,"lamp_position":[lamps[0].position.x,lamps[0].position.y,lamps[0].position.z]})
    shot_frame+=1
    if shot_frame>=total_frames+15:
        write_json_atomic(output+"/shot-recipe.json",{"fps":30,"size":[1920,1080],"duration":total_frames/30.0,"direction_seconds":params.direction_seconds,"params":params,"saved_selection":selection,"trajectory":trajectory,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name()})
        print("SAVED_LIGHTING_RECORDING_DONE frames=",total_frames)
        quit()
    return false
