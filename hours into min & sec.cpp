#include<iostream>
using namespace std;
int main()
{
	//converting  hours into min
	float hours;
	cout<<"How many hours want to convert into min & sec : ";
	cin>>hours;
	int min= hours *60;
	cout<<hours<< "Hours in min : "<<min<<endl;
	// converting hours into seconds
	int sec = hours * 3600;
	cout<<hours<<"Hours in sec : "<<sec;
	return 0;
}
