import pifacedigitalio
from Tkinter import *
import time
from threading import Thread

class Config():
    def __init__(self, name, device_id):
        self.name = name
	self.device_id = device_id
        
hlt_config = Config("HLT", "28-0000042dd80d")   

# 1-wire Thermometer
class Thermometer():
    def __init__(self, device_id):
	self.device_id = device_id

    def read_temp(self):
        print "read temp"
	tfile = open("/sys/bus/w1/devices/" + self.device_id + "/w1_slave")
        text = tfile.read()
        tfile.close()
        secondline = text.split("\n")[1]
        temperaturedata = secondline.split(" ")[9]
        temperature = float(temperaturedata[2:])/1000
        return temperature

# Heat control modes
class ControlMode():
    off = 0
    on = 1
    tc = 2
    tc_delayed = 3
    pwm = 4
    pwm_delayed = 5

# Heat control states
class ControlState():
    off = 0
    tc = 1
    tc_stopping = 2
    tc_delayed = 3
    pwm = 4
    pwm_stopping = 5
    pwm_delayed = 6

class Events():
    btn_off = 0
    btn_tc = 1
    btn_pwm = 2
    controller_stopped = 3
    btn_pwm_delay = 4
    btn_tc_delay = 5
    timer_expired = 6

# Controller base class
class Controller():
    def __init__(self, stopped_cb):
        self.target = 0
        self.mode = ControlMode.off
        self.turned_on = 0
        self.stopped_cb = stopped_cb

    def set_target(self, target):
        self.target = target
        print "set target " + str(target)
 
    def start(self):
        th = Thread(target = self.start_delay())
        th.start()
  
    def start_delay(self):
        time.sleep(2)
        print "starting"
        self.mode = ControlMode.on

        # Start control thread
        run_th = Thread(target = self.run)
        run_th.start()

    def stop(self):
        print "stopping"
        self.mode = ControlMode.off
 
    def run(self):
        while (self.mode == ControlMode.on):
            self.control()
        self.turn_off()
        self.stopped_cb(Events.controller_stopped)

    def control(self):
        print "not implemented"

    def turn_on(self):
        if (self.turned_on == 0):
     	    pifacedigital = pifacedigitalio.PiFaceDigital()
	    pifacedigital.output_pins[4].turn_on()
            time.sleep(0.05)
	    pifacedigital.output_pins[5].turn_on()
	    time.sleep(0.05)
	    pifacedigital.output_pins[6].turn_on()
            print "turn heat on"
	    self.turned_on = 1

    def turn_off(self):
        self.turned_on = 0
     	pifacedigital = pifacedigitalio.PiFaceDigital()
	pifacedigital.output_pins[4].turn_off()
        time.sleep(0.05)
	pifacedigital.output_pins[5].turn_off()
        time.sleep(0.05) 
	pifacedigital.output_pins[6].turn_off()
        print "turning heat off"


# Temperature Control
class TempControl(Controller):
    def __init__(self, stopped_cb, device_id):
        Controller.__init__(self, stopped_cb)
	self.deadband = 0.5
        self.temp = 0
        self.thermometer = Thermometer(device_id)

    def control(self):
        self.temp = self.thermometer.read_temp()
        print self.temp
        if ((self.temp + self.deadband) < self.target):
            if (self.turned_on != 1):
                print "temp control turning heat on"
                self.turn_on()
        else:
            if (self.turned_on != 0):
                print "temp setpoint reached"
                self.turn_off()
        time.sleep(1)

        
# PWM Control
class PwmControl(Controller):
    def __init__(self, stopped_cb):
        Controller.__init__(self, stopped_cb)
        self.period = 4
	        
    def control(self):
        self.turn_on()
        print "pwm on time = " + str(self.target * self.period)
        time.sleep(self.target * self.period)
        self.turn_off()
        print "pwm off time = " + str((1 - self.target) * self.period)
        time.sleep((1 - self.target) * self.period)
     	self.turn_off()

# Timer
class Timer():
    def __init__(self, expire_cb):
        self.i = 1
        self.seconds = 0
        self.expire_cb = expire_cb

    def start(self, seconds):
        print "delay timer starting"
        self.seconds = seconds
        self.t = Thread(target = self.timer)
        self.t.start()

    def stop(self):
        print "stop delay timer"
        self.seconds = 0
 
    def is_running(self):
        try:
            return self.t.is_alive()
        except:
            return 0

    def timer(self):
        while (self.seconds > 0):
            time.sleep(1)
            print self.seconds
            self.seconds -= 1

            # Let the man upstairs know that the timer has expired
            if (self.seconds == 0):
                print "timer expiring"
                self.expire_cb(Events.timer_expired)

root = Tk()


class BrewControllerGui():
    def __init__(self, col_offset, name, device_id, event_cb):
        self.name = name
        self.device_id = device_id        

        # Init widgets
	self.t = DoubleVar()
        self.col_offset = col_offset
        self.init_frame()
        self.init_temp()
        self.init_control_btns()
        self.init_temp_inputs()

        # Hook up callback for gui events
        self.event_cb = event_cb

    def init_frame(self):
        self.frm = Frame(root, relief = RIDGE, borderwidth = 5)
        self.frm.grid(row = 0, column = self.col_offset, sticky = "w")
        self.title = Label(self.frm, text = self.name, font = ("Purisa", 50))
        self.title.grid(row = 0, column = 0, stick = "w")

    def init_temp(self):
        self.temp = Label(self.frm, textvariable = self.t)
        self.temp.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 75))
        self.temp.grid(row = 3, column = 0, columnspan = 2, rowspan = 5, stick = "w")
        
    def init_control_btns(self):
        self.btn_var = IntVar()
        self.btn_tc =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc, command = self.temp_btn_tc_cb)
        self.btn_tc.config(width = 20, text = "Temperature Control", indicatoron = 0, font = ("Purisa", 20))
        self.btn_tc.grid(row = 10, column = 0, sticky = "we", columnspan = 3)
        self.btn_pwm = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm, command = self.temp_btn_pwm_cb)
        self.btn_pwm.config(width = 20, text = "PWM", indicatoron = 0, font = ("Purisa", 20))
	self.btn_pwm.grid(row = 11, column = 0, sticky = "we", columnspan = 3)

        self.btn_tc_delay =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc_delayed, command = self.temp_btn_tc_delay_cb)
        self.btn_tc_delay.config(width = 20, text = "Temperature Control Later", indicatoron = 0, font = ("Purisa", 20))
        self.btn_tc_delay.grid(row = 12, column = 0, sticky = "we", columnspan = 3)

        self.btn_pwm_delay = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm_delayed, command = self.temp_btn_pwm_delay_cb)
	self.btn_pwm_delay.config(width = 25,text = "PWM Later ", indicatoron = 0, font = ("Purisa", 20))
        self.btn_pwm_delay.grid(row = 13, column = 0, sticky = "we", columnspan = 3)

        self.btn_off = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.off, command = self.temp_btn_off_cb)
	self.btn_off.config(width = 20,text = "Off", indicatoron = 0, font = ("Purisa", 20))
        self.btn_off.grid(row = 14, column = 0, sticky = "we", columnspan = 3, pady = (0,20)) 
        
    def init_temp_inputs(self):
        self.temp_target = IntVar()
        self.pwm_target = IntVar()
        self.temp_label_target = Label(self.frm, text = "Temp", font = ("Purisa", 15))
        self.temp_label_target.grid(row = 15, column = 0, sticky = "w")
        self.temp_input_target = Spinbox(self.frm, from_ = 0, to = 100, textvariable = self.temp_target, command = self.temp_input_target_cb)
        self.temp_input_target.config(width = 5, font = ("Purisa", 15))
        self.temp_input_target.grid(row = 15, column = 1, sticky = "we") 
        self.temp_label_pwm = Label(self.frm, text = "PWM", font = ("Purisa", 15))
        self.temp_label_pwm.grid(row = 16, column = 0, sticky = "w")
        self.temp_input_pwm = Spinbox(self.frm, from_ = 10, to = 100, textvariable = self.pwm_target, command = self.pwm_input_target_cb)
        self.temp_input_pwm.config(width = 5, font = ("Purisa", 15))
	self.temp_input_pwm.grid(row = 16, column = 1, sticky = "we")

    def btn_tc_update(self, is_stopping):
        self.btn_tc.select()
        if (is_stopping):
            self.btn_tc.config(text = "Temperature Control Stopping")
        else:
            self.btn_tc.config(text = "Temperature Control")

    def btn_pwm_update(self, is_stopping):
        self.btn_pwm.select()
        if (is_stopping):
            self.btn_pwm.config(text = "PWM Stopping")
        else:
            self.btn_pwm.config(text = "PWM")

    def temp_btn_tc_cb(self):
        self.event_cb(Events.btn_tc)

    def temp_btn_tc_delay_cb(self): 
        self.event_cb(Events.btn_tc_delay)

    def temp_btn_pwm_cb(self):
        self.event_cb(Events.btn_pwm)

    def temp_btn_pwm_delay_cb(self):
        self.event_cb(Events.btn_pwm_delay)
        
    def temp_btn_off_cb(self):
	self.event_cb(Events.btn_off)

    def temp_input_target_cb(self):
        self.temp_controller.set_target(self.temp_target.get())

    def pwm_input_target_cb(self):
        self.pwm_controller.set_target(float(self.pwm_target.get()) / 100)
        

# Statemachine
class Statemachine():
    def __init__(self, start_state, next_cb):
        self._state = start_state
        self.next_cb = next_cb

    def next(self, next_state):
        self._state = next_state
        self.next_cb()

    def get_state(self):
        return self._state

    state = property(get_state, next)
    

# Brew controller incorpating temp control,
# pwm and delay timer
class BrewController():
    def __init__(self, name, device_id):
        self.sm = Statemachine(ControlState.off, self.init_state)
        self.gui = BrewControllerGui(0, name, device_id, self.process_event)
        self.temp_controller = TempControl(self.process_event, device_id)
        self.pwm_controller = PwmControl(self.process_event)
        self.pwm_delay_timer = Timer(self.process_event)
        self.tc_delay_timer = Timer(self.process_event)

        root.protocol("WM_DELETE_WINDOW", self.close_cb)

    def process_event(self, event):
        if (self.sm.state == ControlState.off):
            if (event == Events.btn_tc):
                self.sm.next(ControlState.tc)
            elif (event == Events.btn_pwm):
                self.sm.next(ControlState.pwm)
            elif (event == Events.btn_pwm_delay):
                self.sm.next(ControlState.pwm_delayed)
            elif (event == Events.btn_tc_delay):
                self.sm.next(ControlState.tc_delayed)

        elif (self.sm.state == ControlState.tc):
            if (event == Events.btn_off):
                self.sm.next(ControlState.tc_stopping)

        if (self.sm.state == ControlState.tc_stopping):
            if (event == Events.controller_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.tc_delayed):
            if (event == Events.btn_tc_delay):
                self.sm.next(ControlState.tc_delayed)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.tc)
                
        elif (self.sm.state == ControlState.pwm):
            if (event == Events.btn_off):
                self.sm.next(ControlState.pwm_stopping)

        elif (self.sm.state == ControlState.pwm_stopping):
            if (event == Events.controller_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.pwm_delayed):
            if (event == Events.btn_pwm_delay):
                self.sm.next(ControlState.pwm_delayed)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.pwm)

    def init_state(self):
        if (self.sm.state == ControlState.tc):
            self.temp_controller.start()
            self.gui.btn_tc_update(0)
            
        elif (self.sm.state == ControlState.tc_stopping):
            self.temp_controller.stop()
            self.gui.btn_tc_update(1)

        elif (self.sm.state == ControlState.tc_delayed):
            self.tc_delay_timer.start(10)

        elif (self.sm.state == ControlState.pwm):
            self.pwm_controller.start()
            self.gui.btn_pwm_update(0)

        elif (self.sm.state == ControlState.pwm_stopping):
            self.pwm_controller.stop()
            self.gui.btn_pwm_update(1)

        elif (self.sm.state == ControlState.pwm_delayed):
            self.pwm_delay_timer.start(10)
   
        elif (self.sm.state == ControlState.off):
            self.gui.btn_tc_update(0)
            self.gui.btn_pwm_update(0)            

    def turn_off_everything(self):
	self.temp_controller.stop()
	self.pwm_controller.stop()
	self.pwm_delay_timer.stop()

    # Handle window close
    def close_cb(self):
        self.turn_off_everything()
        root.quit()
         
        
b = BrewController("HLT", "28-0000042dd80d")

       


    


class Gui():
    def __init__(self, col_offset, name, device_id):
        self.name = name
        self.device_id = device_id        

        # Init widgets
	self.t = DoubleVar()
        self.col_offset = col_offset
        self.init_frame()
        self.init_temp()
        self.init_control_btns()
        self.init_temp_inputs()
        self.init_delay_timer()

        # Init objects
        self.init_temp_controller()
        self.init_pwm_controller()
        self.init_thermometer(device_id)
        self.init_pwm_delay_timer()
        self.init_tc_delay_timer()

        # Start temp read thread
        self.th = Thread(target = self.read_temp)
        self.th.start()

    def init_frame(self):
        self.frm = Frame(root, relief = RIDGE, borderwidth = 5)
        self.frm.grid(row = 0, column = self.col_offset, sticky = "w")
        self.title = Label(self.frm, text = self.name, font = ("Purisa", 50))
        self.title.grid(row = 0, column = 0, stick = "w")

    def init_temp(self):
        self.temp = Label(self.frm, textvariable = self.t)
        self.temp.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 75))
        self.temp.grid(row = 3, column = 0, columnspan = 2, rowspan = 5, stick = "w")
        
    def init_control_btns(self):
        self.btn_var = IntVar()
        self.btn_tc =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc, command = self.temp_btn_tc_cb)
        self.btn_tc.config(width = 20, text = "Temperature Control", indicatoron = 0, font = ("Purisa", 20))
        self.btn_tc.grid(row = 10, column = 0, sticky = "we", columnspan = 3)
        self.btn_pwm = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm, command = self.temp_btn_pwm_cb)
        self.btn_pwm.config(width = 20, text = "PWM", indicatoron = 0, font = ("Purisa", 20))
	self.btn_pwm.grid(row = 11, column = 0, sticky = "we", columnspan = 3)

        self.btn_tc =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc_delayed, command = self.temp_btn_tc_delay_cb)
        self.btn_tc.config(width = 20, text = "Temperature Control Later", indicatoron = 0, font = ("Purisa", 20))
        self.btn_tc.grid(row = 12, column = 0, sticky = "we", columnspan = 3)

        self.btn_pwm_delay = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm_delayed, command = self.temp_btn_pwm_delay_cb)
	self.btn_pwm_delay.config(width = 25,text = "PWM Later ", indicatoron = 0, font = ("Purisa", 20))
        self.btn_pwm_delay.grid(row = 13, column = 0, sticky = "we", columnspan = 3)

        self.btn_off = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.off, command = self.temp_btn_off_cb)
	self.btn_off.config(width = 20,text = "Off", indicatoron = 0, font = ("Purisa", 20))
        self.btn_off.grid(row = 14, column = 0, sticky = "we", columnspan = 3, pady = (0,20)) 
        
    def init_temp_inputs(self):
        self.temp_target = IntVar()
        self.pwm_target = IntVar()
        self.temp_label_target = Label(self.frm, text = "Temp", font = ("Purisa", 15))
        self.temp_label_target.grid(row = 15, column = 0, sticky = "w")
        self.temp_input_target = Spinbox(self.frm, from_ = 0, to = 100, textvariable = self.temp_target, command = self.temp_input_target_cb)
        self.temp_input_target.config(width = 5, font = ("Purisa", 15))
        self.temp_input_target.grid(row = 15, column = 1, sticky = "we") 
        self.temp_label_pwm = Label(self.frm, text = "PWM", font = ("Purisa", 15))
        self.temp_label_pwm.grid(row = 16, column = 0, sticky = "w")
        self.temp_input_pwm = Spinbox(self.frm, from_ = 10, to = 100, textvariable = self.pwm_target, command = self.pwm_input_target_cb)
        self.temp_input_pwm.config(width = 5, font = ("Purisa", 15))
	self.temp_input_pwm.grid(row = 16, column = 1, sticky = "we")

    def init_delay_timer(self):
        self.delay_time = IntVar()
        self.delay_time.set(0)
	self.delay_timer_label = Label(self.frm, text = "Delay Time (hours)", font = ("Purisa", 15))
        self.delay_timer_label.grid(row = 17, column = 0, sticky = "w")
        self.delay_timer_input = Spinbox(self.frm, from_ = 0, to = 24, textvariable = self.delay_time, command = self.delay_timer_input_cb)
        self.delay_timer_input.config(width = 5, font = ("Purisa", 15))
        self.delay_timer_input.grid(row = 17, column = 1, sticky = "we") 

    def init_temp_controller(self):	
        self.temp_controller = TempControl(self.device_id)
        self.temp_controller.set_target(71)
 	self.btn_var.set(ControlMode.off)
	self.temp_target.set(71) 

    def init_pwm_controller(self):
        self.pwm_controller = PwmControl()
 
        self.pwm_controller.set_target(0.5)
 	self.btn_var.set(ControlMode.off)
        self.pwm_target.set(50)

    def init_thermometer(self, device_id):
        self.thermometer = Thermometer(device_id)

    def init_pwm_delay_timer(self):
        self.pwm_delay_timer = Timer(self.pwm_delay_timer_expired_cb)

    def init_tc_delay_timer(self):
        self.tc_delay_timer = Timer(self.tc_delay_timer_expired_cb)

    def temp_btn_tc_cb(self):
        self.turn_off_everything()
        self.temp_controller.start()

    def temp_btn_tc_delay_cb(self):
        self.turn_off_everything()
        print "start timer"
        self.tc_delay_timer.start(10)

    def temp_btn_pwm_cb(self):
        self.turn_off_everything()
        self.pwm_controller.start()

    def temp_btn_pwm_delay_cb(self):
        self.turn_off_everything()
        print "start timer"
        self.pwm_delay_timer.start(10)
        
    def temp_btn_off_cb(self):
	self.turn_off_everything()

    def temp_input_target_cb(self):
        self.temp_controller.set_target(self.temp_target.get())

    def pwm_input_target_cb(self):
        self.pwm_controller.set_target(float(self.pwm_target.get()) / 100)

    def delay_timer_input_cb(self):
        dt = self.delay_time.get()
        
    def pwm_delay_timer_expired_cb(self):
        self.btn_var.set(ControlMode.pwm)
        self.temp_btn_pwm_cb()

    def tc_delay_timer_expired_cb(self):
        self.btn_var.set(ControlMode.tc)
	self.temp_btn_tc_cb()

    def turn_off_everything(self):
	self.temp_controller.stop()
	self.pwm_controller.stop()
        self.pwm_delay_timer.stop()
        self.tc_delay_timer.stop()

    def pwm_delay_timer_update(self):
        if (self.pwm_delay_timer.is_running()):
            s = self.pwm_delay_timer.seconds
            self.btn_pwm_delay.config(text = "PWM Later " + time.strftime("%H:%M:%S", time.gmtime(s)))
        else:
            self.btn_pwm_delay.config(text = "PWM Later")

    def tc_delay_timer_update(self):
        if (self.tc_delay_timer.is_running()):
            s = self.pwm_delay_timer.seconds
            self.btn_pwm_delay.config(text = "PWM Later " + time.strftime("%H:%M:%S", time.gmtime(s)))
        else:
            self.btn_pwm_delay.config(text = "PWM Later")

    def read_temp(self):
        while(1):
            self.t.set(round(self.thermometer.read_temp(),1))
	    self.pwm_delay_timer_update()
            self.tc_delay_timer_update()    
 
                
#gui = Gui(0, "HLT", "28-0000042dd80d") 

# Handle window close
#def close_cb():
#    gui.turn_off_everything()
#    root.quit()
#root.protocol("WM_DELETE_WINDOW", close_cb)

root.mainloop()
