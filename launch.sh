cat > ~/Halloween_Slots/launch.sh << 'EOF'
#!/bin/bash
export DISPLAY=:0
cd ~/Halloween_Slots
python3 main.py
EOF