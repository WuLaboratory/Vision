% 1. Define Parameters
Fs = 1000;            % Sampling frequency (Hz)
T = 1/Fs;             % Sampling period
L = 1000;             % Length of signal
t = (0:L-1)*T;        % Time vector
ff = 2*3.14159./t;


%Draw a line
A = 2;
B = 3;
y = A*t + B;

figure
plot(t,y)

%1 A = 10, B = 1
%2 A = 5, B = 1.5
%3 A = 2, B = 3

%Draw a sinusoidal curve
AA = 2.3;
w = 3;
C = 7;
yy = AA*sin(w*t+C);

figure
plot(t,yy)

%1 AA = 2, w = 5, C = 0
%2 AA = 3, w = 9, C = -4
%3 AA = 2.3, w = 3, C = 7

%Draw a quadratic curve
AAA = 5;
BBB = 8;
CCC = 13;
yyy = AAA.*t.*t + BBB*t + CCC;

figure
plot(t,yyy)

%1 AAA = 1, BBB = 2, CCC = 3
%2 AAA = 5, BBB = 8, CCC = 13
