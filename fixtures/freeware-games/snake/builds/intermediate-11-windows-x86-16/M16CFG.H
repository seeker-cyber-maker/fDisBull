/* Generated source-bound Win16 configuration, ANSI CP1252 chrome. */
static const Fdb16Key fdb_keys[] = {{"ArrowDown",0UL,80UL},{"ArrowLeft",0UL,75UL},{"ArrowRight",0UL,77UL},{"ArrowUp",0UL,72UL},{"Escape",27UL,1UL},{"KeyA",97UL,30UL},{"KeyD",100UL,32UL},{"KeyN",110UL,49UL},{"KeyP",112UL,25UL},{"KeyR",114UL,19UL},{"KeyS",115UL,31UL},{"KeyW",119UL,17UL},{"KeyX",120UL,45UL},{"Space",32UL,57UL}};
static const Fdb16Color fdb_colors[] = {{0UL,0,0,0},{1UL,0,0,170},{2UL,0,170,0},{8UL,85,85,85},{10UL,85,255,85},{12UL,255,85,85},{15UL,255,255,255}};
static const char *const region_0_names[] = {"lfsr16","original"};
static const char *const region_0_labels[] = {"LFSR16 \267 changes food placement","Original LCG"};
static const Fdb16Region fdb_regions[] = {{"rng","Random generator",2,1,region_0_names,region_0_labels}};
static const char *const function_names[] = {"action","render","reset","rng","step"};
static const Fdb16Config configuration = {70000UL,4096UL,320UL,200UL,54.925493230640853,630UL,631UL,632UL,633UL,634UL,635UL,636UL,616UL,1UL,2UL,0UL,14UL,7UL,1UL,5UL,fdb_keys,fdb_colors,fdb_regions,function_names,"Snake \267 recovered DOS fixture","Click the game to focus. Arrows/WASD turn, Space/P pauses, N steps, R resets and Esc quits. You can also click the blue controls. Starts paused. The random-generator selector changes future food placements without restarting. Original matches the DOS generator; LFSR16 is experimental.","de88dfc2e117068d60060f9105220b30794ef68957aa081abf2ebe6458f433ff",1764648354UL};
