extends "res://tools/lighting-control/cardinal_scene.gd"

var state_dir := ""
var revision := -1
var elapsed := 0.0
var poll_clock := 0.0
var capture_clock := 0.0
var capturing := false
var phase := 0
var sequence := 0

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("--lighting-state="):state_dir=arg.trim_prefix("--lighting-state=")
    super._initialize()

func _process(delta: float) -> bool:
    if not active:return false
    poll_clock+=delta
    capture_clock+=delta
    if poll_clock>.08:
        poll_clock=0
        var candidate=JSON.parse_string(FileAccess.get_file_as_string(state_dir+"/current.json"))
        if candidate is Dictionary and int(candidate.revision)!=revision:
            params=candidate.params
            revision=int(candidate.revision)
            apply_parameters()
    if revision<0:return false
    if not bool(params.paused):elapsed+=delta
    phase=int(floor(elapsed/float(params.direction_seconds)))%4 if bool(params.auto_cycle) else int(params.direction)
    var offset: Vector3=light_offsets()[phase]
    var local_seconds:=fmod(elapsed,float(params.direction_seconds))
    if bool(params.auto_cycle) and elapsed>=float(params.direction_seconds) and local_seconds<.8:
        offset=light_offsets()[posmod(phase-1,4)].lerp(offset,smoothstep(0.0,1.0,local_seconds/.8))
    pose_and_light(elapsed,offset,true)
    if capture_clock>.14 and not capturing:
        capture_clock=0
        capturing=true
        call_deferred("capture")
    return false

func capture() -> void:
    await RenderingServer.frame_post_draw
    sequence+=1
    var name:="frame-"+str(sequence%2)+".png"
    var image:=root.get_texture().get_image()
    image.save_png(state_dir+"/"+name+".tmp")
    DirAccess.rename_absolute(state_dir+"/"+name+".tmp",state_dir+"/"+name)
    write_json_atomic(state_dir+"/rendered.json",{"revision":revision,"params":params.duplicate(true),"sequence":sequence,"image":name,"direction":phase,"animation_frame":actors[0].animation_frame,"clay_animation_frame":actors[1].animation_frame,"renderer":RenderingServer.get_current_rendering_method(),"adapter":RenderingServer.get_video_adapter_name(),"lamp_position":[lamps[0].position.x,lamps[0].position.y,lamps[0].position.z]})
    capturing=false
