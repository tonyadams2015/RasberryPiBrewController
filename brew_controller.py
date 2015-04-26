try:
    import pifacedigitalio
except ImportError:
    print "import failed for pifacedigitalio"
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
        try:
            print "read temp"
            tfile = open("/sys/bus/w1/devices/" + self.device_id + "/w1_slave")
            text = tfile.read()
            tfile.close()
            secondline = text.split("\n")[1]
            temperaturedata = secondline.split(" ")[9]
            temperature = float(temperaturedata[2:])/1000
            return temperature
        except IOError:
            return 0


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
    tc_delayed_stopping = 4
    pwm = 5
    pwm_stopping = 6
    pwm_delayed = 7
    pwm_delayed_stopping = 8
    disabled = 9

class Events():
    btn_off = 0
    btn_tc = 1
    btn_pwm = 2
    controller_stopped = 3
    btn_pwm_delay = 4
    btn_tc_delay = 5
    timer_expired = 6
    set_tc = 7
    set_pwm = 8
    set_pwm_delay_time = 9
    set_tc_delay_time = 10
    timer_stopped = 11
    enable = 12
    disable =13

# Controller base class
class Controller():
    def __init__(self, stopped_cb, heat_cb):
        self.target = 0
        self.mode = ControlMode.off
        self.turned_on = 0
        self.stopped_cb = stopped_cb
        self.heat_cb = heat_cb
        try:
            self.pifacedigital = pifacedigitalio.PiFaceDigital()
        except NameError:
            print "pifacedigital is not available on this platform"

    def set_target(self, target):
        self.target = target
        print "set target " + str(target)
  
    def start(self):
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
            try:
                self.control()
            except:
                 raise 
        self.turn_off()
        self.stopped_cb(Events.controller_stopped)

    def control(self):
        print "not implemented"

    def turn_on(self):
        if (self.turned_on == 0):
            try:
                self.pifacedigital.output_pins[4].turn_on()
                time.sleep(0.05)
                self.pifacedigital.output_pins[5].turn_on()
                time.sleep(0.05)
                self.pifacedigital.output_pins[6].turn_on()
            except AttributeError:
                print "pifacedigital is not available on this platform"
            print "turn heat on"
        self.turned_on = 1
        self.heat_cb(1)

    def turn_off(self):
        self.turned_on = 0
        try:
            self.pifacedigital.output_pins[4].turn_off()
            time.sleep(0.05)
            self.pifacedigital.output_pins[5].turn_off()
            time.sleep(0.05) 
            self.pifacedigital.output_pins[6].turn_off()
        except AttributeError:
                print "pifacedigital is not available on this platform"
        print "turning heat off"
        self.heat_cb(0)


# Temperature Control
class TempControl(Controller):
    def __init__(self, stopped_cb, heat_cb, device_id):
        Controller.__init__(self, stopped_cb, heat_cb)
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
    def __init__(self, stopped_cb, heat_cb):
        Controller.__init__(self, stopped_cb, heat_cb)
        self.period = 4
        self.latch = 0

    def control(self):
        self.turn_on()
        print "pwm on time = " + str(self.target * self.period)
        time.sleep(self.target * self.period)

        if (self.target == 1):
            self.latch = 1
        else:
            self.latch = 0

        if (self.latch != 1):
            self.turn_off()
            print "pwm off time = " + str((1 - self.target) * self.period)
            time.sleep((1 - self.target) * self.period)
     	    self.turn_off()

# Timer
class Timer():
    def __init__(self, expire_cb, stopped_cb, timer_update_cb):
        self.i = 1
        self.seconds = 0
        self.expire_cb = expire_cb
        self.stopped_cb = stopped_cb
        self.timer_update_cb = timer_update_cb

    def start(self, seconds):
        print "delay timer starting"
        self.seconds = seconds
        self.t = Thread(target = self.timer)
        self.t.start()

    def stop(self):
        print "stop delay timer"
        self.seconds = 0
        self.stopped_cb(Events.timer_stopped)
 
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
            self.timer_update_cb(self.seconds)

            # Let the man upstairs know that the timer has expired
            if (self.seconds == 0):
                print "timer expiring"
                self.expire_cb(Events.
                               timer_expired)

        # Expired ot stopped
        self.timer_update_cb(0)
                

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
        self.init_btn_enable()
        self.init_status()
        self.init_timer_display()

        # Hook up callbacks for gui events
        self.event_cb = event_cb

        # Start temp read thread
        self.thermometer = Thermometer(self.device_id)
        self.th = Thread(target = self.read_temp)
        self.th.start()

    def init_frame(self):
        self.frm = Frame(root, relief = RIDGE, borderwidth = 5)
        self.frm.grid(row = 0, column = self.col_offset, sticky = "w")
        self.title = Label(self.frm, text = self.name, font = ("Purisa", 50))
        self.title.grid(row = 0, column = 0, columnspan = 2 ,stick = "w")

    def init_btn_enable(self):
        self.enable = IntVar()
        self.enable.set(0)
        self.btn_enable =  Checkbutton(self.frm, variable = self.enable, command = self.btn_enable_cb)
        self.btn_enable.config(text = "Enable", font = ("Purisa", 16))
        self.btn_enable.grid(row = 0, column = 1)
        self.enable_all(0)

    def init_temp(self):
        self.temp = Label(self.frm, textvariable = self.t)
        self.temp.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 50))
        self.temp.grid(row = 4, column = 0, columnspan = 1, rowspan = 5, stick = "w")

    def init_status(self):
        self.heat_status = StringVar()
        self.heat_status.set("heat off")
        self.lab_heat_status = Label(self.frm, textvariable = self.heat_status)
        self.lab_heat_status.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 16))
        self.lab_heat_status.grid(row = 4, column = 1, columnspan = 1, rowspan = 1, stick = "we")
        self.lab_heat_status.config(background = "blue")

    def init_timer_display(self):
        self.time_left = StringVar()
        self.lab_seconds = Label(self.frm, textvariable = self.time_left)
        self.lab_seconds.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 16))
        self.lab_seconds.grid(row = 5, column = 1, columnspan = 1, rowspan = 1, stick = "we")
 
    def init_control_btns(self):
        self.btn_var = IntVar()
        self.btn_tc =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc, command = self.temp_btn_tc_cb)
        self.btn_tc.config(text = "Temp Control", indicatoron = 0, font = ("Purisa", 17))
        self.btn_tc.grid(row = 10, column = 0, sticky = "we", columnspan = 2)
        self.btn_pwm = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm, command = self.temp_btn_pwm_cb)
        self.btn_pwm.config(text = "PWM", indicatoron = 0, font = ("Purisa", 17))
        self.btn_pwm.grid(row = 11, column = 0, sticky = "we", columnspan = 2)

        self.btn_tc_delay =  Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.tc_delayed, command = self.temp_btn_tc_delay_cb)
        self.btn_tc_delay.config(text = "Temp Control Later", indicatoron = 0, font = ("Purisa", 17))
        self.btn_tc_delay.grid(row = 12, column = 0, sticky = "we", columnspan = 2)

        self.btn_pwm_delay = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.pwm_delayed, command = self.temp_btn_pwm_delay_cb)
        self.btn_pwm_delay.config(width = 25,text = "PWM Later ", indicatoron = 0, font = ("Purisa", 17))
        self.btn_pwm_delay.grid(row = 13, column = 0, sticky = "we", columnspan = 2)

        self.btn_off = Radiobutton(self.frm, variable = self.btn_var, value = ControlMode.off, command = self.temp_btn_off_cb)
        self.btn_off.config(width = 20,text = "Off", indicatoron = 0, font = ("Purisa", 17))
        self.btn_off.grid(row = 14, column = 0, sticky = "we", columnspan = 2, pady = (0,20)) 
        
    def init_temp_inputs(self):
        self.temp_target = IntVar()
        self.pwm_target = IntVar()
        self.delay_time = IntVar()       
        self.temp_label_target = Label(self.frm, text = "Temp", font = ("Purisa", 15))
        self.temp_label_target.grid(row = 15, column = 0, sticky = "w")
        self.temp_input_target = Spinbox(self.frm, from_ = 0, to = 100, textvariable = self.temp_target, command = self.temp_input_target_cb)
        self.temp_input_target.config(width = 5, font = ("Purisa", 15))
        self.temp_input_target.grid(row = 15, column = 1, sticky = "we") 
        self.temp_label_pwm = Label(self.frm, text = "PWM", font = ("Purisa", 15))
        self.temp_label_pwm.grid(row = 16, column = 0, sticky = "w")
        self.temp_input_pwm = Spinbox(self.frm, from_ = 10, to = 100, textvariable = self.pwm_target, command = self.pwm_input_target_cb)
        self.temp_input_pwm.config(width = 5, font = ("Purisa", 15), values = (10,20,30,40,50,60,70,75,80,85,90,95,100))
        self.temp_input_pwm.grid(row = 16, column = 1, sticky = "we")
        self.label_delay_time = Label(self.frm, text = "Delay Timer", font = ("Purisa", 15))
        self.label_delay_time.grid(row = 17, column = 0, sticky = "w")
        self.input_delay_time = Spinbox(self.frm, from_ = 1, to = 24, textvariable = self.delay_time, command = self.input_delay_time_cb)
        self.input_delay_time.config(width = 5, font = ("Purisa", 15))
        self.input_delay_time.grid(row = 17, column = 1, sticky = "we")

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

    def set_tc_input_target(self, target):
        self.temp_target.set(target)

    def set_pwm_input_target(self, target):
        self.pwm_target.set(target)
        
    def set_input_delay_time(self, delay_time):
        self.delay_time.set(delay_time)
        
    def btn_off_update(self):
        self.btn_off.select()

    def temp_btn_tc_cb(self):
        self.event_cb(Events.btn_tc)

    def temp_btn_tc_delay_cb(self): 
        self.event_cb(Events.btn_tc_delay)

    def temp_btn_pwm_cb(self):
        self.event_cb(Events.btn_pwm)

    def btn_pwm_enable(self, enable):
        if (enable):
            self.btn_pwm.config(state = NORMAL)
        else:
            self.btn_pwm.config(state = DISABLED)

    def btn_tc_enable(self, enable):
        if (enable):
            self.btn_tc.config(state = NORMAL)
        else:
            self.btn_tc.config(state = DISABLED)

    def btn_tc_delay_enable(self, enable):
        if (enable):
            self.btn_tc_delay.config(state = NORMAL)
        else:
            self.btn_tc_delay.config(state = DISABLED) 

    def btn_pwm_delay_enable(self, enable):
        if (enable):
            self.btn_pwm_delay.config(state = NORMAL)
        else:
            self.btn_pwm_delay.config(state = DISABLED) 

    def enable_all(self, enable):
        self.btn_pwm_enable(enable)
        self.btn_tc_enable(enable)
        self.btn_tc_delay_enable(enable)
        self.btn_pwm_delay_enable(enable)

        if (enable == 0):
            self.btn_tc.deselect()
            self.btn_pwm.deselect()
            self.btn_pwm_delay.deselect()
            self.btn_tc_delay.deselect()
            self.btn_off.select()

    def btn_enable_cb(self):
        if (self.enable.get() == 1):
            self.event_cb(Events.enable)
        else:
            self.event_cb(Events.disable)
        
    def temp_btn_pwm_delay_cb(self):
        self.event_cb(Events.btn_pwm_delay)
        
    def temp_btn_off_cb(self):
            self.event_cb(Events.btn_off)

    def temp_input_target_cb(self):
        self.event_cb(Events.set_tc, self.temp_target.get())

    def pwm_input_target_cb(self):
        self.event_cb(Events.set_pwm, float(self.pwm_target.get()) / 100)

    def input_delay_time_cb(self):
        self.event_cb(Events.set_pwm_delay_time, float(self.delay_time.get()))
        self.event_cb(Events.set_tc_delay_time, float(self.delay_time.get()))

    def read_temp(self):
        while(1):
            self.t.set(round(self.thermometer.read_temp(),1))

    def update_heat_status(self, heat_status):
        if (heat_status == 1):
            self.heat_status.set("heat on")
            self.lab_heat_status.config(background = "red")
        else:
            self.heat_status.set("heat off")
            self.lab_heat_status.config(background = "blue")

    def update_timer_display(self, seconds):
        s = time.strftime("%H:%M:%S", time.gmtime(seconds))
        self.time_left.set(s)

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
    def __init__(self, **kwargs):
        # Init objects
        self.sm = Statemachine(ControlState.off, self.init_state)
        self.gui = BrewControllerGui(kwargs['col_offset'], kwargs['name'], kwargs['device_id'] , self.process_event)
        self.temp_controller = TempControl(self.process_event, self.gui.update_heat_status, kwargs['device_id'])
        self.pwm_controller = PwmControl(self.process_event, self.gui.update_heat_status)
        self.pwm_delay_timer = Timer(self.process_event, self.process_event, self.gui.update_timer_display)
        self.tc_delay_timer = Timer(self.process_event, self.process_event, self.gui.update_timer_display)

        # Init defaults
        self.default_tc_target = kwargs['tc_default']
        self.default_pwm_target = kwargs['pwm_default']
        self.default_delay_time = kwargs['delay_time_default']
        self.init_defaults()

        self.pwm_delay_time = self.default_delay_time
        self.tc_delay_time = self.default_delay_time
        
        root.protocol("WM_DELETE_WINDOW", self.close_cb)

        # Init state
        self.sm.next(ControlState.disabled)

    def process_event(self, event, *args):

        # setpoint set events get processed no matter what state we are in.
        # So do these first

        if (event == Events.set_tc):
           self.temp_controller.set_target(args[0])
           return
        elif (event == Events.set_pwm):
           self.pwm_controller.set_target(args[0])
           return
        elif (event == Events.set_pwm_delay_time):
           self.pwm_delay_time = args[0]
           return
        elif (event == Events.set_tc_delay_time):
           self.tc_delay_time = args[0]
           return

        # Disable works from any state
        if (event == Events.disable):
            self.sm.next(ControlState.disabled)

        # Process events that depend on state
        if (self.sm.state == ControlState.disabled):
            if (event == Events.enable):
                self.sm.next(ControlState.off)
                
        elif (self.sm.state == ControlState.off): 
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
            if (event == Events.btn_off):
                self.sm.next(ControlState.tc_delayed_stopping)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.tc)

        elif (self.sm.state == ControlState.tc_delayed_stopping):
            if (event == Events.timer_stopped):
                self.sm.next(ControlState.off)
                
        elif (self.sm.state == ControlState.pwm):
            if (event == Events.btn_off):
                self.sm.next(ControlState.pwm_stopping)

        elif (self.sm.state == ControlState.pwm_stopping):
            if (event == Events.controller_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.pwm_delayed):
            if (event == Events.btn_off):
                self.sm.next(ControlState.pwm_delayed_stopping)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.pwm)

        elif (self.sm.state == ControlState.pwm_delayed_stopping):
            if (event == Events.timer_stopped):
                self.sm.next(ControlState.off)
                
    def init_state(self):
        if (self.sm.state == ControlState.tc):
            self.temp_controller.start()
            self.gui.btn_tc_update(0)
            self.gui.btn_pwm_enable(0)
            self.gui.btn_tc_delay_enable(0)
            self.gui.btn_pwm_delay_enable(0)
            
        elif (self.sm.state == ControlState.tc_stopping):
            self.temp_controller.stop()
            self.gui.btn_tc_update(1)

        elif (self.sm.state == ControlState.tc_delayed):
            self.tc_delay_timer.start(int(self.tc_delay_time) * 3600)
            self.gui.btn_pwm_enable(0)
            self.gui.btn_tc_enable(0)
            self.gui.btn_pwm_delay_enable(0)
            self.gui.btn_tc_delay_enable(1)

        elif (self.sm.state == ControlState.tc_delayed_stopping):
            self.tc_delay_timer.stop()

        elif (self.sm.state == ControlState.pwm):
            self.pwm_controller.start()
            self.gui.btn_pwm_update(0)
            self.gui.btn_tc_enable(0)
            self.gui.btn_tc_delay_enable(0)
            self.gui.btn_pwm_delay_enable(0)

        elif (self.sm.state == ControlState.pwm_stopping):
            self.pwm_controller.stop()
            self.gui.btn_pwm_update(1)

        elif (self.sm.state == ControlState.pwm_delayed):
            print "starting timer"
            self.pwm_delay_timer.start(int(self.pwm_delay_time)* 3600)
            self.gui.btn_pwm_enable(0)
            self.gui.btn_tc_enable(0)
            self.gui.btn_pwm_delay_enable(1)
            self.gui.btn_tc_delay_enable(0)           

        elif (self.sm.state == ControlState.pwm_delayed_stopping):
            self.pwm_delay_timer.stop()

        elif (self.sm.state == ControlState.off):
            self.gui.btn_tc_update(0)
            self.gui.btn_pwm_update(0)
            self.gui.btn_off_update()
            self.gui.enable_all(1)
            self.gui.update_timer_display(0)

        elif (self.sm.state == ControlState.disabled):
            self.gui.enable_all(0)
            self.turn_off_everything()

    def turn_off_everything(self):
	self.temp_controller.stop()
	self.pwm_controller.stop()
	self.pwm_delay_timer.stop()
	self.tc_delay_timer.stop()

    # Handle window close
    def close_cb(self):
        self.turn_off_everything()
        root.quit()
         
    def init_defaults(self):
        self.gui.set_tc_input_target(self.default_tc_target)
        self.gui.set_pwm_input_target(self.default_pwm_target)
        self.gui.set_input_delay_time(self.default_delay_time)
        self.pwm_controller.set_target(float(self.default_pwm_target) / 100)
        self.temp_controller.set_target(int(self.default_tc_target))
        
hlt = BrewController(col_offset = 0, name = "HLT", device_id = "28-0000042dd80d", tc_default = "71", pwm_default = "50", delay_time_default = "12")
kettle = BrewController(col_offset = 1, name = "Kettle", device_id = "28-0000042dd80d", tc_default = "95", pwm_default = "50", delay_time_default = "12")
mt = BrewController(col_offset = 2, name = "Mash", device_id = "28-0000042dd80d", tc_default = "71", pwm_default = "50", delay_time_default = "12")

root.mainloop()
