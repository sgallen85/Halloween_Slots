audio_extension='.ogg'
#window_size=(960, 540)
window_size=(1920, 1080)
window_size=True

servo_min = 370
servo_max = 575

gpio_button = 17

num_servos = 0

theme = "halloween"
background_file = 'halloween2.jpg'

pumpkin_symbol = 5

win_banner_hold_seconds = 5.0

#configure win precentages
win_odds = {
    'none':    0.0,
    'double':  0.0,
    'triple':  0.995,
    'jackpot': 0.05,
}

idle_music_timeout = 20.0

start_with_music = False 


#configure LED 
#Keep set to pin 21 to avoid conflicts with audio.
led_pin = 21
led_channel = 0
led_count = 100
#led_idle_colors = [(255, 50, 0), (0, 200, 15)]   # any number of colors, cycled in order
led_pulse_seconds = 4.0                          # time for one color to fade up from dark and back down
led_pulse_gap = 0.0001                              # seconds fully dark before the next color starts
#led_runner_color = (140, 0, 255)                 # purple runner between pulses
led_runner_seconds = 3.0                         # runner's trip down the strip and back (0 = off)
#led_runner_background_level = 0.6                # brightness of the steady color under the runner, 0-1
#led_spin_colors = [(255, 50, 0), (0, 200, 15)]   # every-other-LED colors while the reels spin
led_spin_interval = 0.2                          # seconds between spin colors swapping places
#led_win_colors = [(0, 200, 15), (140, 0, 255), (255, 50, 0), (170, 170, 170)]  # win show: green, purple, orange, white
led_brightness = 100                          # overall strip brightness 0-255
led_runner_seconds = 8.0                  # runner speed (round trip)
led_runner_background_level = 0.3       # 1.0 = full-brightness background, lower = more contrast

#configure music lights (idle lights follow the background music)
#Run make_light_maps.py after adding new songs to audio/background/.
led_music_lights = True                  # False = start with the pulse/runner loop (L key toggles)
led_music_offset = 0.0                   # seconds; raise if lights run early, lower if late ([ / ] keys adjust live)
led_music_beats_per_color = 16           # beats before the color changes
#led_music_colors = [(255, 50, 0), (0, 200, 15), (140, 0, 255)]   # beat colors: orange, green, purple
