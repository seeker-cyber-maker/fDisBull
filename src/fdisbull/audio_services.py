"""Authored INT66 selector contracts; these do not verify a resident handler."""

REFERENCE = 'https://fd.lod.bz/rbil/interrup/sound/'
SAMPLE_DESCRIPTOR = dict(name='SNDSTRUC', size=12, endian='little', fields=[
    dict(offset=0, size=4, name='sample', type='far_pointer_offset_segment'),
    dict(offset=4, size=2, name='length_bytes', type='uint16'),
    dict(offset=6, size=4, name='playing_flag', type='far_pointer_offset_segment'),
    dict(offset=10, size=2, name='frequency_hz', type='uint16')])

# Unknown/variant register details deliberately remain unspecified. Naming a
# selector does not supply an executable implementation or an effect receipt.
DIGPAK = {
    0x688:('play_sample', {'ds:si':'sample_descriptor'}, {}),
    0x689:('sound_status', {}, {'ax':'playback_status_zero_when_idle'}),
    0x68a:('preformat_audio', {'ds:si':'sample_descriptor'}, {}),
    0x68b:('play_preformatted_sample', {'ds:si':'sample_descriptor'}, {}),
    0x68c:('audio_capabilities', {}, {'ax':'capability_flags','dx':'fixed_rate_if_applicable'}),
    0x68d:('playback_address', {}, {}),
    0x68e:('set_completion_callback', {'dx:bx':'callback','ds':'callback_data_segment'}, {}),
    0x68f:('stop_sample', {}, {}),
    0x690:('set_hardware_legacy', {}, {}),
    0x691:('callback_address', {}, {}),
    0x692:('restore_hardware_vectors', {}, {}),
    0x693:('set_timer_divisor', {}, {}),
    0x694:('play_loop', {'ds:si':'sample_descriptor'}, {}),
    0x695:('post_pending_sample', {'ds:si':'sample_descriptor'}, {}),
    0x696:('pending_status', {}, {}),
    0x697:('set_stereo_pan', {}, {}),
    0x698:('set_play_mode', {}, {}),
    0x699:('status_addresses', {}, {}),
    0x69a:('set_record_mode', {}, {}),
    0x69b:('stop_next_loop', {}, {}),
    0x69c:('set_dma_backfill_mode', {}, {}),
    0x69d:('dma_counter', {}, {}),
    0x69e:('verify_dma_block', {}, {}),
    0x69f:('set_pcm_volume', {}, {}),
    0x6a0:('set_dpmi_mode', {}, {}),
}
MIDPAK = {
    0x700:('uninstall', {}, {}),
    0x701:('digital_capabilities', {}, {}),
    0x702:('play_sequence', {'bx':'sequence_number'}, {'ax':'zero_playing_one_unavailable'}),
    0x703:('segue_sequence', {}, {}),
    0x704:('register_xmidi', {'cx:bx':'xmidi_data','di:si':'data_length_bytes_high_low'},
           {'ax':'registration_status_zero_failed_one_resident_two_application'}),
    0x705:('stop_music', {}, {}),
    0x706:('remap_channel_legacy', {}, {}),
    0x707:('trigger_event_counter', {}, {}),
    0x708:('reset_trigger_event_counter', {}, {}),
    0x709:('sleep_legacy', {}, {}),
    0x70a:('awake_legacy', {}, {}),
    0x70b:('resume_playing', {}, {}),
    0x70c:('sequence_status', {}, {'ax':'zero_stopped_one_playing_two_done'}),
    0x70d:('register_xmidi_file', {'cx:bx':'filename'}, {}),
    0x70e:('relative_volume', {}, {}),
    0x70f:('set_relative_volume', {'bx':'new_volume','cx':'time'}, {}),
    0x710:('load_driver', {'bx':'adv_segment','cx':'required_zero_offset','dx:si':'instrument_bank'}, {}),
    0x711:('poll', {}, {}),
    0x712:('midi_clock', {}, {}),
    0x713:('trigger_count_address', {}, {}),
    0x714:('event_id_address', {}, {}),
    0x716:('sequence_number', {}, {}),
}
