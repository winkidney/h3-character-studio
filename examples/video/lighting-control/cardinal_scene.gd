extends SceneTree
## Shared scene and parameter application for interactive preview and final capture.
var actors: Array = []
var cameras: Array[Camera3D] = []
var lamps: Array[OmniLight3D] = []
var environments: Array[Environment] = []
var active := false
var params: Dictionary = {"energy":0.7,"ambient":0.0,"normal_strength":0.8,"normals_enabled":true,"silver_enabled":true,"color":"#ffffff","horizontal_extent":1.6,"vertical_extent":1.6,"front_offset":1.3,"range":8.0,"playback_scale":0.46875,"direction_seconds":6.0,"direction":0,"auto_cycle":false,"paused":false,"frame":11}
const LIGHT_NAMES := ["上方照射","下方照射","左侧照射","右侧照射"]

func _initialize() -> void:
    root.set_flag(Window.FLAG_NO_FOCUS,true)
    root.size=Vector2i(1920,1080)
    call_deferred("begin")

func begin() -> void:
    var ui := Control.new()
    root.add_child(ui)
    ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var scenes: Array = []
    var views: Array[SubViewport] = []
    for panel in range(2):
        var container := SubViewportContainer.new()
        container.position=Vector2(panel*960,0)
        container.size=Vector2(960,1080)
        ui.add_child(container)
        var view := SubViewport.new()
        view.size=Vector2i(960,1080)
        view.own_world_3d=true
        view.render_target_update_mode=SubViewport.UPDATE_ALWAYS
        container.add_child(view)
        var scene=load("res://scenes/ancient_canal.tscn").instantiate()
        view.add_child(scene)
        scenes.append(scene)
        views.append(view)
    for i in range(30):await physics_frame
    for panel in range(2):
        var scene=scenes[panel]
        var world := Node3D.new()
        views[panel].add_child(world)
        scene.player.controls_enabled=false
        scene.player.paused=true
        scene.player.preview_walk=true
        scene.player.frame_override=-1
        scene.player.direction_override=3
        scene.player.facing=3
        scene.player.set_physics_process(false)
        scene.values.normals_enabled=true
        scene.values.normal_strength=float(params.normal_strength)
        scene.values.clay=panel==1
        scene.player.apply_material(scene.values)
        scene.player.reparent(world)
        scene.player.position=Vector3.ZERO
        scene.player.velocity=Vector3.ZERO
        scene.camera.reparent(world)
        scene.camera.position=Vector3(0,1.10,4.6)
        scene.camera.look_at(Vector3(0,1.10,0),Vector3.UP)
        scene.camera.fov=35
        scene.camera.current=true
        actors.append(scene.player)
        cameras.append(scene.camera)
        var environment := Environment.new()
        environment.background_mode=Environment.BG_COLOR
        environment.background_color=Color(.032,.047,.065)
        environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
        environment.ambient_light_energy=0
        environment.reflected_light_source=Environment.REFLECTION_SOURCE_DISABLED
        environments.append(environment)
        environment.tonemap_mode=Environment.TONE_MAPPER_FILMIC
        var env_node := WorldEnvironment.new()
        env_node.environment=environment
        world.add_child(env_node)
        var lamp := OmniLight3D.new()
        lamp.light_color=Color.WHITE
        lamp.light_energy=float(params.energy)
        lamp.omni_range=8.0
        lamp.shadow_enabled=false
        lamp.position=Vector3(0,1.1,0)+light_offsets()[0]
        world.add_child(lamp)
        lamps.append(lamp)
        scene.queue_free()
    for i in range(4):await process_frame
    active=true

func light_offsets() -> Array[Vector3]:
    var h: float=float(params.horizontal_extent)
    var v: float=float(params.vertical_extent)
    var z: float=float(params.front_offset)
    return [Vector3(0,v,z),Vector3(0,-v,z),Vector3(-h,0,z),Vector3(h,0,z)]

func apply_parameters() -> void:
    for panel in range(2):
        lamps[panel].light_energy=float(params.energy)
        lamps[panel].light_color=Color(str(params.color))
        lamps[panel].omni_range=float(params.range)
        environments[panel].ambient_light_energy=float(params.ambient)
        environments[panel].ambient_light_color=Color.WHITE
        actors[panel].surface.set_shader_parameter("normal_strength",float(params.normal_strength))
        actors[panel].surface.set_shader_parameter("use_normals",bool(params.normals_enabled))
        actors[panel].surface.set_shader_parameter("polished_silver",1.0 if bool(params.silver_enabled) else 0.0)
        actors[panel].surface.set_shader_parameter("silver_specular",1.0 if bool(params.silver_enabled) else 0.0)

func pose_and_light(seconds: float,offset: Vector3,use_pause: bool) -> void:
    for panel in range(2):
        actors[panel].inspection_clock=seconds*float(params.playback_scale)
        actors[panel].frame_override=int(params.frame) if use_pause and bool(params.paused) else -1
        actors[panel].update_animation()
        lamps[panel].position=Vector3(0,1.1,0)+offset

func write_json_atomic(path: String,data: Dictionary) -> void:
    var file:=FileAccess.open(path+".tmp",FileAccess.WRITE)
    file.store_string(JSON.stringify(data))
    file.close()
    DirAccess.rename_absolute(path+".tmp",path)
