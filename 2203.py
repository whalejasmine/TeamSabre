import pandas
import pyomo.opt
import pyomo.environ as pe
import scipy
import itertools
import cplex
import logging

#DEFINE GLOBAL NAMES HERE
CREWDATA_CSV = 'CrewData.csv'
DEMANDDATA_CSV = 'DemandData.csv'
VACATIONDATA_CSV = 'VacationData.csv'

crew_df = pandas.read_csv(CREWDATA_CSV)
demand_df = pandas.read_csv(DEMANDDATA_CSV)
vacation_df = pandas.read_csv(VACATIONDATA_CSV)

def get_demand(rank, fleet, base, week):
	# example: base = "B1", fleet = "A330", rank = "FO", week = 0
	# return the demand at B1, A330, FO of week 0
	return demand_df['B'+ str(base) + '_' + fleet[1:] + rank][week]

def get_nonfix_pilots():
	return set(crew_df[(crew_df.Bid_BaseChange.notnull()) | (crew_df.Bid_FleetChange.notnull())| (crew_df.Bid_RankChange.notnull())]['Crew_ID'])

def get_all_pilots():
	return set(crew_df[crew_df.Rank != "SIM_INS"]['Crew_ID'])

def get_vacation(model, p, t):
	vacations = {
		'900201' : [2,3,7,8],
		'900488' : [3,4,14,15],
		'900387' : [4,7],
		'900369' : [4,5,6],
		'800000' : [2,3],
		'700125' : [11]
	}
	pilot = str(p)
	if pilot in vacations:
		if t+1 in vacations[pilot]:
			return 300
		else:
			return 0
	else:
		return 0
####trainer Pilots
trainers = set(crew_df[(crew_df.Instructor == "TR3233_1")]['Crew_ID'])

#### Seniority set[1,2,3,4]
se_1 = set(crew_df[(crew_df.Seniority == 1)]['Crew_ID'])
se_2 = set(crew_df[(crew_df.Seniority == 2)]['Crew_ID'])
se_3 = set(crew_df[(crew_df.Seniority == 3)]['Crew_ID'])
se_4 = set(crew_df[(crew_df.Seniority == 4)]['Crew_ID'])

####fixedPos
def print_duplicate(a):
	print [item for item, count in collections.Counter(a).items() if count > 1]

nonfixed_df = crew_df[(crew_df.Bid_BaseChange.notnull()) | (crew_df.Bid_FleetChange.notnull())| (crew_df.Bid_RankChange.notnull())]
fixed_df = crew_df[(~crew_df.Bid_BaseChange.notnull()) & (~crew_df.Bid_FleetChange.notnull()) & (~crew_df.Bid_RankChange.notnull())]

#### toPos
topos_list = []
rank_change = set(crew_df[(crew_df.Bid_RankChange.notnull())]['Crew_ID'])
fleet_change = set(crew_df[(crew_df.Bid_FleetChange.notnull())]['Crew_ID'])
base_change = set(crew_df[(crew_df.Bid_BaseChange.notnull())]['Crew_ID'])

for pilot in set(nonfixed_df['Crew_ID']):
	cur = [pilot]
	pilot_item = crew_df[crew_df.Crew_ID == pilot]
	if pilot in rank_change:
		print pilot_item
		cur.append('CPT')
		cur.append(pilot_item.Cur_Fleet.values[0])
		cur.append(pilot_item.Current_Base.values[0])
	elif pilot in fleet_change :
		cur.append(pilot_item.Rank.values[0])
		cur.append(pilot_item.Bid_FleetChange.values[0])
		cur.append(pilot_item.Current_Base.values[0])
	elif pilot in base_change :
		cur.append(pilot_item.Rank.values[0])
		cur.append(pilot_item.Cur_Fleet.values[0])
		cur.append(pilot_item.Bid_BaseChange.values[0])
	topos_list.append(cur)

toPos = pandas.DataFrame(topos_list)
toPos.columns =['ID','RANK','FLEET','BASE']

#### fromPos
frompos_list = []
for pilot in set(nonfixed_df['Crew_ID']):
	cur = [pilot]
	pilot_item = crew_df[crew_df.Crew_ID == pilot]
	cur.append(pilot_item.Rank.values[0])
	cur.append(pilot_item.Cur_Fleet.values[0])
	cur.append(pilot_item.Current_Base.values[0])
	frompos_list.append(cur)

fromPos = pandas.DataFrame(frompos_list)
fromPos.columns =['ID','RANK','FLEET','BASE']

# ALL debuged before this point

model = pe.ConcreteModel()
model.pilots = pe.Set(initialize=get_all_pilots())
nonfix_var_set=[]
fix_var_set = []
all_var_set = []
from_set = []
to_set = []

for pilot in nonfixed_df['Crew_ID'].values:
		for fleet in ['A320','A330']:
			for base in [1,2]:
				for rank in ['CPT','FO']:
					in_from = pilot in fromPos[(fromPos.RANK==rank)&(fromPos.FLEET==fleet)&(fromPos.BASE==base)]['ID'].values
					in_to = pilot in toPos[(toPos.RANK==rank)&(toPos.FLEET==fleet)&(toPos.BASE==base)]['ID'].values
					if(in_from or in_to):
						nonfix_var_set.append((pilot,rank,fleet,base))
						all_var_set.append((pilot,rank,fleet,base))
					if in_from :
						from_set.append((pilot,rank,fleet,base))
					if in_to :
						to_set.append((pilot,rank,fleet,base))

df_fixnew = fixed_df.set_index(['Crew_ID','Rank','Cur_Fleet','Current_Base'])
for pilot in fixed_df['Crew_ID'].values:
		for fleet in ['A320','A330']:
			for base in [1,2]:
				for rank in ['CPT','FO']:
					if (pilot, rank, fleet, base) in df_fixnew.index:
						fix_var_set.append((pilot, rank, fleet, base))
						all_var_set.append((pilot, rank, fleet, base))


model.nonfix_pilots = pe.Set(initialize = nonfixed_df['Crew_ID'].values)
model.fix_pilots = model.pilots - model.nonfix_pilots

model.nonfix_var_set = pe.Set(initialize = nonfix_var_set)
model.fix_var_set = pe.Set(initialize = fix_var_set)
model.all_var_set = pe.Set(initialize = all_var_set)

model.trainer_pilots = pe.Set(initialize = trainers)
model.rank_pilots = pe.Set(initialize = rank_change)
model.fleet_pilots = pe.Set(initialize = fleet_change)
model.base_pilots = pe.Set(initialize = base_change)
model.from_pos = pe.Set(initialize = from_set)
model.to_pos = pe.Set(initialize = to_set)
#new set
nonfixed_trainer=[]
for pilot in nonfixed_df['Crew_ID'].values:
	if pilot in model.trainer_pilots:
		nonfixed_trainer.append(pilot)
model.trainer_nonfix_pilots = pe.Set(initialize = nonfixed_trainer)
#end new set
model.se_1 = pe.Set(initialize = se_1)
model.se_2 = pe.Set(initialize = se_2)
model.se_3 = pe.Set(initialize = se_3)
model.se_4 = pe.Set(initialize = se_4)

model.fix_pilots = model.pilots - model.nonfix_pilots
model.rank = pe.Set(initialize=['CPT','FO'])
model.fleet = pe.Set(initialize=['A330','A320'])
model.base = pe.Set(initialize=[1,2])
model.time = pe.Set(initialize=range(len(demand_df)))
model.timestart = pe.Set(initialize=range(len(demand_df)-1))
if len(demand_df) <= 12:
	model.quarterstart = pe.Set(initialize = [0])
elif len(demand_df) >12 & len(demand_df) <= 26:
	model.quarterstart = pe.Set(initialize = [0,13])
elif len(demand_df) >26 & len(demand_df) <= 40:
	model.quarterstart = pe.Set(initialize = [0,13,26])
model.train_start_time = pe.Set(initialize=range(len(demand_df)-2))
model.endtime = len(damand_df)-1

model.Y = pe.Var(model.nonfix_var_set*model.time, domain=pe.Binary)
# this variable contained all pilots
model.Yall = pe.Var(model.all_var_set*model.time, domain=pe.Binary)
model.Ynowork = pe.Var(model.all_var_set*model.time, domain=pe.Binary)
model.shortage = pe.Var(model.rank*model.fleet*model.base*model.time, domain = pe.NonNegativeIntegers)
model.surplus = pe.Var(model.rank*model.fleet*model.base*model.time, domain = pe.NonNegativeIntegers)
model.Trainer = pe.Var(model.trainer_pilots*model.base*model.time, domain=pe.Binary)
model.Trainee = pe.Var(model.fleet_pilots*model.base*model.time, domain=pe.Binary)
model.V = pe.Var(model.pilots*model.time, domain=pe.Binary)
model.VP = pe.Var(model.pilots*model.quarterstart, domain=pe.NonNegativeIntegers)
#only nonfix pilots can take vacation or training?
model.Vnonfix_position = pe.Var(model.nonfix_var_set*model.time, domain=pe.Binary)
model.Vfix_position = pe.Var(model.fix_var_set*model.time, domain=pe.Binary)
model.Trainer_pos = pe.Var(model.trainer_pilots*model.rank*model.fleet*model.base*model.time, domain=pe.Binary)
model.Trainee_pos = pe.Var(model.fleet_pilots*model.rank*model.fleet*model.base*model.time, domain=pe.Binary)
model.VS = pe.Var(model.pilots*model.time, domain = pe.NonNegativeIntegers)

model.short_cost = pe.Param(model.rank*model.fleet*model.base*model.time, initialize = 70000)
model.base_transition_cost = pe.Param(model.nonfix_var_set*model.time, initialize = 15000)
model.fleet_transition_cost = pe.Param(model.nonfix_var_set*model.time, initialize = 5000)
model.vacation_penalty = pe.Param(model.pilots*model.quarterstart, initialize = 300)
model.seniority_reward = pe.Param(model.pilots*model.time, initialize = 50)


def daily_cost(model, p, rank, fleet, base,time):
    if rank == 'CPT':
        if fleet == 'A320':
            if (p in model.se_1):
                return 500
            elif (p in model.se_2):
                return 500*1.1
            elif (p in model.se_3):
                return 500*1.1*1.1
            elif (p in model.se_4):   
                return 500*1.1*1.1*1.1
        else:
            if (p in model.se_1):
                return 800
            elif (p in model.se_2):
                return 800*1.1
            elif (p in model.se_3):
                return 800*1.1*1.1
            elif (p in model.se_4):   
                return 800*1.1*1.1*1.1  
    elif rank == 'FO':
        if fleet == 'A320':
            if (p in model.se_1):
                return 400
            elif (p in model.se_2):
                return 400*1.1
            elif (p in model.se_3):
                return 400*1.1*1.1
            elif (p in model.se_4):   
                return 400*1.1*1.1*1.1
        else:
            if (p in model.se_1):
                return 600
            elif (p in model.se_2):
                return 600*1.1
            elif (p in model.se_3):
                return 600*1.1*1.1
            elif (p in model.se_4):   
                return 600*1.1*1.1*1.1                    

model.dailycost = pe.Param(model.all_var_set*model.time, initialize = daily_cost)
model.vacation_reward = pe.Param(model.pilots*model.time, initialize = get_vacation)


#include fixed
def trainer_rule(model,p,b,t):
	rhs = 0
	for f in model.fleet:
		for r in model.rank:
			if (p,r,f,b) in model.all_var_set:
				rhs=rhs+model.Yall[p,r,f,b,t]
	return model.Trainer[p,b,t] <= rhs
model.trainer_constraint = pe.Constraint(model.trainer_pilots*model.base*model.time,rule=trainer_rule)

def pilot_on_work1(model, p, r, f, b,t):
    return  model.Ynowork[p,r,f,b,t] <= model.Yall[p,r,f,b,t]
model.pilotonwork1 = pe.Constraint(model.all_var_set*model.time,rule=pilot_on_work1)

def trainee_rule(model,p,b,t):
	rhs=0
	for f in model.fleet:
		for r in model.rank:
			if (p,r,f,b) in model.nonfix_var_set:
				rhs=rhs+model.Y[p,r,f,b,t]	
	return model.Trainee[p,b,t] <= rhs
model.trainee_constraint = pe.Constraint(model.fleet_pilots*model.base*model.time,rule=trainee_rule)

def vacation_rule1(model,p,b,t):
	return model.V[p,t] <= 1- model.Trainer[p,b,t]
model.vacation_constraint1 = pe.Constraint(model.trainer_pilots*model.base*model.time,rule=vacation_rule1)

def vacation_rule2(model,p,b,t):
	return model.V[p,t] <= 1- model.Trainee[p,b,t]
model.vacation_constraint2 = pe.Constraint(model.fleet_pilots*model.base*model.time,rule=vacation_rule2)
#include fixed
def training_rule(model,p,r,f,b,t):
	if (p,r,f,b) in model.all_var_set:
		return model.Trainer_pos[p,r,f,b,t] >= model.Trainer[p,b,t] + model.Yall[p,r,f,b,t]-1
	else:
		return pe.Constraint.Skip
model.training_constraint = pe.Constraint(model.trainer_pilots*model.rank*model.fleet*model.base*model.time,rule = training_rule)
#
def training_rule_onwork(model,p,r,f,b,t):
	if (p,r,f,b) in model.all_var_set:
		return model.Ynowork[p,r,f,b,t] <= model.Trainer_pos[p,r,f,b,t]
	else:
		return pe.Constraint.Skip
model.training_constraint_onwork = pe.Constraint(model.trainer_pilots*model.rank*model.fleet*model.base*model.time,rule = training_rule_onwork)

def trainee_rule2(model,p,r,f,b,t):
	if p in model.fleet_pilots:
		if(t >= 2):
			return model.Trainee_pos[p,r,f,b,t] >= model.Trainee[p,b,t] + model.Trainee[p,b,t-1] + model.Trainee[p,b,t-2] +model.Y[p,r,f,b,t] -1
		elif(t >= 1):
			return model.Trainee_pos[p,r,f,b,t] >= model.Trainee[p,b,t] + model.Trainee[p,b,t-1]+model.Y[p,r,f,b,t] -1
		else:
			return model.Trainee_pos[p,r,f,b,t] >= model.Trainee[p,b,t] + model.Y[p,r,f,b,t] -1
	else:
		return pe.Constraint.Skip
model.trainee_constraint2 = pe.Constraint(model.nonfix_var_set*model.time, rule = trainee_rule2)

def trainee_rule2_onwork(model,p,r,f,b,t):
	if (p,r,f,b) in model.all_var_set:
		return  model.Ynowork[p,r,f,b,t] <= model.Trainee_pos[p,r,f,b,t]
	else:
		return pe.Constraint.Skip
model.trainee_constraint2_onwork = pe.Constraint(model.fleet_pilots*model.rank*model.fleet*model.base*model.time, rule = trainee_rule2_onwork)

def demand_rule(model,r,f,b,t):
	vp=0
	for p in model.nonfix_pilots :
		if (p, r, f, b) in model.nonfix_var_set:
			vp +=model.Vnonfix_position[p, r, f, b, t]

	tp=0
	for p in model.trainer_pilots :
		if (p, r, f, b) in model.all_var_set:
			tp +=model.Trainer_pos[p, r, f, b, t]

	traineep=0
	for p in model.fleet_pilots :
		if (p, r, f, b) in model.nonfix_var_set:
			traineep +=model.Trainee_pos[p, r, f, b, t]
	vfixp=0
	for p in model.fix_pilots :
		if (p, r, f, b) in model.fix_var_set:
			vfixp +=model.Vfix_position[p, r, f, b, t]

	curr_fixed = fixed_df[(fixed_df.Rank==r)&(fixed_df.Cur_Fleet==f)&(fixed_df.Current_Base==b)]['Crew_ID'].values
	pilot = len(curr_fixed)
	nonfix_pilot = 0
	for p in model.nonfix_pilots :
		if (p, r, f, b) in model.nonfix_var_set:
			nonfix_pilot +=model.Y[p, r, f, b, t]
	rhs = pilot + nonfix_pilot - vp - tp - vfixp - traineep + model.shortage[r,f,b,t] - model.surplus[r,f,b,t]
	demand = get_demand(r,f,b,t)
	return rhs == demand 
model.demand_constraint = pe.Constraint(model.rank*model.fleet*model.base*model.time, rule = demand_rule)
# model.Demand.pprint()

#at time t, a pilot should occupy one and only one position
#checked
def pilot_pos_rule(model, p, t):
	summ=0
	for r in model.rank:
		for f in model.fleet:
			for b in model.base:
				if (p,r,f,b) in model.nonfix_var_set:
					summ += model.Y[p, r, f, b, t]
	lhs = summ
	return lhs == 1
model.PositionConst = pe.Constraint(model.nonfix_pilots*model.time, rule = pilot_pos_rule)
# model.PositionConst.pprint()

# all nonfix_pilots should start being at their "from" position
def pilot_transit_rule0(model, p, r, f, b):
	return model.Y[p,r,f,b,0] == 1
model.Transition0 = pe.Constraint(model.from_pos, rule = pilot_transit_rule0)
# model.Transition0.pprint()

# all nonfix_pilots should transit only once--"from" postion should be decreasing
def pilot_transit_rule1(model, p, r, f, b, t):
	return model.Y[p,r,f,b,t] - model.Y[p,r,f,b,t+1] >= 0
model.Transition1 = pe.Constraint(model.from_pos*model.timestart, rule = pilot_transit_rule1)
# model.Transition1.pprint()

# "to" postion should be increasing
def pilot_transit_rule2(model, p, r, f, b, t):
	return model.Y[p,r,f,b,t] - model.Y[p,r,f,b,t+1] <= 0
model.Transition2 = pe.Constraint(model.to_pos*model.timestart, rule = pilot_transit_rule2)
# model.Transition2.pprint()


def get_slot(t):
	return vacation_df["Available_Vacation_Slots"][t]

 #vacation constraint. -vacation. pilot <= slot. 
def max_vacation_slot_rule(model, t):
	lhs = 0
	for pilot in model.pilots :
		lhs += model.V[pilot,t]
	return lhs <= get_slot(t)  
model.pilot_vacation_slot_exceed = pe.Constraint(model.time, rule = max_vacation_slot_rule)

### at least one vacation per quarter
def min_vacation_rule(model, p, t):
	lhs = 0
	for i in range(13):
		lhs += model.V[p,t+i]
	lhs += model.VP[p,t]
	return lhs >= 1
model.Vacation = pe.Constraint(model.pilots*model.quarterstart, rule = min_vacation_rule)

### Seniority rule: get reward if we give vacation to more senior employee first
def seniority_rule(model,p,t):
	lhs = 0
	if (p in model.se_1):
		lhs = model.V[p,t]*1

	elif (p in model.se_2):
		lhs = model.V[p, t] * 2

	elif (p in model.se_3):
		lhs = model.V[p, t] * 3

	elif (p in model.se_4):
		lhs = model.V[p, t] * 4

	lhs -= model.VS[p, t]
	return lhs == 0
model.seniority = pe.Constraint(model.pilots*model.time, rule = seniority_rule)

### if the pilot p is not at position [b,f,r]at week t, even if he is on vacation, then Vnonfix_position[p,b,f,r,t] = 0
def vacation_position_rule(model,p,r,f,b,t):
	lhs = 0
	lhs = model.V[p,t] + model.Y[p,r,f,b,t] - 1 - model.Vnonfix_position[p,r,f,b,t]
	return lhs <= 0
model.Vacation_position = pe.Constraint(model.nonfix_var_set*model.time, rule = vacation_position_rule)

def vacation_position_rule_onwork(model,p,r,f,b,t):
	return model.Ynowork[p,r,f,b,t] <= model.Vnonfix_position[p,r,f,b,t]
model.Vacation_position_onwork = pe.Constraint(model.nonfix_var_set*model.time, rule = vacation_position_rule_onwork)

def vacation_position_rule2(model,p,r,f,b,t):
	lhs = 0
	lhs = model.V[p,t] + model.Yall[p,r,f,b,t] - 1 - model.Vfix_position[p,r,f,b,t]
	return lhs <= 0
model.Vacation_position2 = pe.Constraint(model.fix_var_set*model.time, rule = vacation_position_rule2)

def vacation_position_rule2_onwork(model,p,r,f,b,t):
	return model.Ynowork[p,r,f,b,t] <= model.Vfix_position[p,r,f,b,t]
model.Vacation_position2_onwork = pe.Constraint(model.fix_var_set*model.time, rule = vacation_position_rule2_onwork)

def trainee_var_binding_rule(model, p, r, f, b, t):
	if(p in fleet_change):
		return model.Y[p,r,f,b,t] - model.Y[p,r,f,b,t+1] - model.Trainee[p, b, t+1] == 0
	else:
		return pe.Constraint.Skip
model.trainee_var_binding = pe.Constraint(model.from_pos*model.timestart, rule=trainee_var_binding_rule)

def trainee_trainer_rule(model, b, t):
	total_trainer = 0
	for p in model.trainer_pilots:
		total_trainer += model.Trainer[p, b, t+2]
	total_trainee = 0
	for p in fleet_change:
		total_trainee += model.Trainee[p, b, t]
	return total_trainer == total_trainee
model.trainee_trainer = pe.Constraint(model.base*model.train_start_time, rule = trainee_trainer_rule)

###Yall and Y binding rule (for non-fix pilot part)
def yall_y_binding_rule(model, p, r, f, b, t):
	return model.Yall[p,r,f,b,t] == model.Y[p,r,f,b,t]
model.yall_y_binding = pe.Constraint(model.nonfix_var_set*model.time, rule = yall_y_binding_rule)

###Yall setting rule(for fix-pilot part)
def yall_setting_rule(model, p, r, f, b, t):
	df_new = fixed_df.set_index(['Crew_ID','Rank','Cur_Fleet','Current_Base'])
	if (p, r, f, b) in df_new.index:
		return model.Yall[p,r,f,b,t] == 1
	else:
		return model.Yall[p,r,f,b,t] == 0
model.yall_setting = pe.Constraint(model.fix_var_set*model.time, rule = yall_setting_rule)


###OBJ###
###Transitions:
model.total_fleet_trans_cost = pe.summation(model.fleet_transition_cost, model.Y, index = [(p, r, f, b, model.endtime) for(p, r, f, b) in model.to_pos if p in model.fleet_pilots ])
model.total_base_trans_cost = pe.summation(model.base_transition_cost, model.Y, index = [(p, r, f, b, model.endtime) for(p, r, f, b) in model.to_pos if p in model.base_pilots ])
model.total_trans_cost = model.total_fleet_trans_cost + model.total_base_trans_cost
###Shortages:
model.total_shortage_cost = pe.summation(model.short_cost, model.shortage)
###Vacation Penalty:
model.total_vacation_penalty = pe.summation(model.vacation_penalty, model.VP)
model.total_seniority_reward = pe.summation(model.seniority_reward, model.VS)
###Vacation reward:
model.total_vacation_reward = pe.summation(model.vacation_reward,model.V)

###Daily operation cost:
model.operationcost = pe.summation(model.dailycost,model.Yall)
model.operationminus = pe.summation(model.dailycost,model.Ynowork)

model.OBJ = pe.Objective(expr = model.total_shortage_cost + model.total_trans_cost + model.total_vacation_penalty + 7*model.operationcost - 7*model.operationminus - model.total_seniority_reward - model.total_vacation_reward, sense=pe.minimize)
solver = pyomo.opt.SolverFactory('cplex')


results = solver.solve(model, tee=True, keepfiles=False)
if (results.solver.status != pyomo.opt.SolverStatus.ok):
	logging.warning('Check solver not ok?')
if (results.solver.termination_condition != pyomo.opt.TerminationCondition.optimal):  
	logging.warning('Check solver optimality?')
model.solutions.load_from(results)
#model.load(results)

print "\nTotal number of non-fix pilots is " + str(len(model.nonfix_pilots))
for (p, r, f, b) in model.from_pos:
	for t in model.timestart:
		if model.Y[p, r, f, b, t].value != model.Y[p, r, f, b, t+1].value:
			print "\nPilot " + str(p) + " changed at week " + str(t)
			if str(p) in model.fleet_pilots :
				print "This is a fleet change from " + str(f) 
			if str(p) in model.rank_pilots :
				print "This is a rank change from " + str(r) 
			if str(p) in model.base_pilots :
				print "This is a base change from " + str(b)
				


print "\nTotal number of TR3233_1 qualified trainers is " + str(len(model.trainer_pilots))
for p in model.trainer_pilots:
	for t in model.timestart:
		for b in model.base:
			if model.Trainer[p, b, t].value == 1 :
				print "trainer " + p + " is training at week " + str(t)	+ " at base " + str(b)


print "\nTotal number of pilot applies for fleet change is " + str(len(model.fleet_pilots))
for p in model.fleet_pilots:
	for t in model.timestart:
 		for b in model.base:
 			if model.Trainee[p, b, t].value == 1 :
 				print "pilot " + p + " receives fleet training at week " + str(t) + " at base " + str(b)
 				
 				
# record the transition in each week
for (p, r, f, b) in model.fix_var_set:
	for t in model.time:
		if(model.Vfix_position[p, r, f, b, t].value == 1):
			print p +" "+str(t) + " Vacation"
		if(p in model.trainer_pilots):
			if(model.Trainer[p,b,t].value == 1):
				print p +" "+str(t) + " Giving Training"

for (p, r, f, b) in model.nonfix_var_set:
	for t in model.time:
		if(model.Vnonfix_position[p, r, f, b, t].value == 1):
			print p +" "+str(t) + " Vacation"
		if(p in model.trainer_pilots):
			if(model.Trainer[p,b,t].value == 1):
				print p +" "+str(t) + " Giving Training"
		if(p in model.fleet_pilots):
			if(model.Trainee[p,b,t].value == 1):
				print p +" "+str(t) + " Receive Training"
		if((p in model.base_pilots) & (t in model.timestart) & ((p,r,f,b) in model.from_pos)):
			if((model.Y[p, r, f, b, t].value == 1) & (model.Y[p, r, f, b, t+1].value == 0)):
				print p +" "+str(t) + " Base change from " + str(b)
		if((p in model.rank_pilots) & (t in model.timestart) & ((p,r,f,b) in model.from_pos)):
			if((model.Y[p, r, f, b, t].value == 1) & (model.Y[p, r, f, b, t+1].value == 0)):
				print p +" "+str(t) + " Rank change from " + str(r)

print '\nTotal cost = ', model.OBJ()
print 'Shortage cost is = ', model.total_shortage_cost()
print 'Transition cost is = ', model.total_trans_cost()
print 'Vacation Penalty is = ', model.total_vacation_penalty()
print 'Seniority Reward is =', model.total_seniority_reward()
print 'Daily Salary Cost is =', model.operationcost()
print 'Minus cost is =', model.operationminus()
print 'Vacation reward is =', model.total_vacation_reward()
#instance.solutions.load_from(results)
#model.solutions.load_from(results)
