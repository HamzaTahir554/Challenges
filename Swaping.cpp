// Auther : Hamza Tahir
#include<iostream>
using namespace std;
int main()
{
	//swaping values with out using third variable
	int no1, no2;
	cout<<"Enter no1 value : ";
	cin>>no1;
	cout<<"Enter no2 value : ";
	cin>>no2;
	
	no1 = no1+no2;
	no2 = no1-no2;
	no1 = no1-no2;
	cout<<"After Swaping : "<<endl;
	cout<<"No1 : "<<no1<<endl;
	cout<<"No2 : "<<no2<<endl;
}
