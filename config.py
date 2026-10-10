audio_extension='.ogg'
#window_size=(960, 540)
window_size=(1920, 1080)
window_size=True

servo_min = 370
servo_max = 575

gpio_button = 18

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
led_count = 200
#led_idle_colors = [(255, 50, 0), (0, 200, 15)]   # any number of colors, cycled in order
led_pulse_seconds = 4.0                          # time for one color to fade up from dark and back down
led_pulse_gap = 0.5                              # seconds fully dark before the next color starts
#led_spin_colors = [(255, 50, 0), (0, 200, 15)]   # every-other-LED colors while the reels spin
led_spin_interval = 0.2                          # seconds between spin colors swapping places
led_jackpot_flash_seconds = 5.0                  # how long the strip flashes after a jackpot
