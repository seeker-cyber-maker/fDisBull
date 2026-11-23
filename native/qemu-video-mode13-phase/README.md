# Native mode-13 source raster phase

The patch follows the exact DOSBox typematic QEMU 10.0.13 source
preimage in the manifest. The native opt-in property is
`-global VGA.x-fdisbull-mode13-phase=on`. It requires the existing precise
primary standard VGA and stopped virtual clock. Its source model is
`qemu-vga-chain4-dosbox-mode13-v1`.

The mode origin comes from the completed color standard VGA mode-13
programming packet. It includes all five sequencer registers and all nine
graphics registers, CRTC unlock and writes 00h–18h, miscellaneous output
and the final attribute-controller display enable. The existing source
admission then requires 320×200 chain-4 geometry with 400 physical display
lines, 449 total lines, retrace starting on line 412 and 6-bit DAC.
The tracker records the native write timestamp with both effective VGA
generations. A changed generation withdraws the setup witness until the
guest completes another packet. A lone reset-register write, the first
stream attach and an explicitly stopped clock cannot create the witness.

The first raster boundary strictly after setup uses phase 0. Subsequent
rasters use phase 1, including a stream opened after warm-up. For
physical line period H and logical row r, the deadline is
`frame_start + floor(H/4) + (2*r + phase)*H`. The complete frame exposes
its physical `source-phase`. The stream exposes its observed
`mode-setup` when a matching setup is available.

The opt-in instrumented sidecar uses format 5 and retains the exact setup,
source raster state, intended deadline and armed native expiry. It admits
a bounded setup stamp only at a stopped source boundary. A partially
matched setup packet refuses capture. Import checks the selected profile
and the stopped VGA geometry and generations before rebinding a fresh
source epoch. The standard mode uses the original format 4 and row
deadlines. Older native instrumented formats keep their existing standard
import path.

A local Darwin arm64 native run saved phase 0 at exactly 65 rows and
loaded into a new process. The setup stamp, partial RGB bytes, intended
deadline and timer expiry were identical with a fresh token and epoch.
Both 200-row futures reproduced their exact callback times and full
image digests across the phase-0 to phase-1 transition. Both owners
exited zero. Separate cold runs preserved the timer before the first
draw at zero rows and during steady phase 1 at 65 rows. The independently authored COM used the BIOS
preserve-framebuffer mode flag so it returned before the first raster
boundary. Its SHA-256 is
`a3cf811904920666736c8829a934854fc9298bfb27e187e8a230066fe36373f3`.
Native producer SHA-256
`cea0a35169d6e51fafa6c32824e208ad2c14c9ec755cb9c9c005cd119c2e478f`.
Private witness SHA-256 values are
`5a8228ff645e128966e085a41708bea2b48a5600873f9394e84c5bf3f2f35727`
for the partial phase-0 save,
`360a502bcb34b7e0121503ea98a78dbac70e4d3c0a0615a9db621789fc71bf51`
before the first draw and
`a9f4dd1b1141e06ba1a942dbffc755a022ed00640824aa4c4b55c6a1f691de6e`
for the partial phase-1 save.

The setup witness is specific to the observed color standard-VGA
programming sequence and geometry. The effective DOSBox-X draw setup
timestamp and general game-level dynamic raster parity remain open.
